from __future__ import annotations

import logging
import time
import zipfile
import json
import dataclasses
from collections.abc import Sequence
from pathlib import Path
import psutil

from selenium.webdriver.remote.webdriver import WebDriver
from src.exceptions import BrowserCrashedError

from src.database.repository import HeidiRepository
from src.database.schemas import SessionMetadata
from src.scraper.note_scraper import NoteScraper
from src.scraper.session_scraper import SessionDiscovery
from src.scraper.transcript_scraper import TranscriptScraper
from src.services.checkpoint_service import CheckpointService
from src.services.screenshot_service import ScreenshotService
from src.services.validation_service import ValidationService
from src.utils.hashing import sha256_text
from src.utils.retry_policy import RetryPolicy


class PlannedRestartSignal(Exception):
    """Raised by process_sessions_batched when a planned browser restart is due.

    Unlike BrowserCrashedError (which indicates an unexpected crash), this signal
    is raised deliberately after processing RESTART_EVERY sessions so that main.py
    can cleanly quit the current driver, create a fresh one, and continue.
    The checkpoint already contains the last_session_id / last_session_url so the
    new browser cycle resumes from exactly the right position.
    """


class ArchiveService:
    def __init__(
        self,
        driver: WebDriver,
        discovery: SessionDiscovery,
        transcript_scraper: TranscriptScraper,
        note_scraper: NoteScraper,
        screenshots: ScreenshotService,
        checkpoint: CheckpointService,
        validation: ValidationService,
        repository: HeidiRepository,
        logger: logging.Logger,
        restart_every: int = 75,
    ):
        self.driver = driver
        self.discovery = discovery
        self.transcript_scraper = transcript_scraper
        self.note_scraper = note_scraper
        self.screenshots = screenshots
        self.checkpoint = checkpoint
        self.validation = validation
        self.repository = repository
        self.logger = logger
        self.exports_dir = Path("exports")
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.restart_every = restart_every

    def process_sessions(self, sessions: Sequence[SessionMetadata]) -> None:
        for ordinal, metadata in enumerate(sessions, start=1):
            # if self.checkpoint.should_skip(ordinal):
            #     self.logger.info("[INFO] Skipping previously processed session %s", ordinal)
            #     continue
            self.process_one(ordinal, metadata)

    def process_sessions_batched(self, batch_size: int = 10) -> None:
        """Archive every session using a decoupled discover-once / extract-by-URL design.

        Phase A -- Discovery (runs once, ever):
            Scroll the Past-sessions list a single time from top to bottom and
            persist every session's metadata (and link, when present) to the
            database. A 'discovery_complete' flag in the checkpoint records that
            this pass finished, so it is never repeated on later runs/restarts.

        Phase B -- Extraction (DB-driven, no scrolling):
            Repeatedly pull the next pending sessions straight from the database
            and open each one directly by URL. Because the work queue lives in the
            DB, resuming after a crash or a planned browser restart is just another
            query -- the scraper never re-scrolls the list to find its place. This
            replaces the old O(N^2) "re-scroll the whole completed prefix on every
            restart" behaviour with O(N).

        Raises:
            PlannedRestartSignal: After `restart_every` sessions to trigger a clean
                                  browser restart in main.py (prevents memory leaks).
            BrowserCrashedError:  On unrecoverable Chrome crashes.
        """
        # Teach the discovery helper how to build direct session URLs for rows
        # whose link was not captured, using a pattern learned from the DB.
        self.discovery.url_prefix = self.repository.get_url_prefix_template()
        if self.discovery.url_prefix:
            self.logger.info("[INFO] Learned session URL prefix: %s", self.discovery.url_prefix)

        # -- Phase A: one-time discovery ---------------------------------------
        if not self.checkpoint.is_discovery_complete():
            self.logger.info(
                "[INFO] === DISCOVERY PHASE: scrolling the full session list once ==="
            )
            try:
                discovered = self.discovery.discover_all()
                self.checkpoint.mark_discovery_complete()
                # Re-learn the prefix now that discovery may have captured links.
                self.discovery.url_prefix = (
                    self.discovery.url_prefix or self.repository.get_url_prefix_template()
                )
                self.logger.info(
                    "[INFO] Discovery complete -- %d sessions catalogued in the database.",
                    len(discovered),
                )
            except Exception as disc_exc:
                # Do NOT mark complete on failure; the next run resumes discovery.
                self.logger.error(
                    "[ERROR] Discovery pass failed: %s. Discovery will resume on next run.",
                    str(disc_exc).split(chr(10))[0],
                )
                raise
        else:
            self.logger.info(
                "[INFO] Discovery already complete -- going straight to extraction."
            )

        # -- Phase B: DB-driven extraction -------------------------------------
        # Continue the ordinal counter across restarts so screenshot folders and
        # zip filenames never collide with those from earlier browser cycles.
        global_ordinal = self.checkpoint.load().get("last_processed_ordinal", 0) or 0
        sessions_this_cycle = 0  # resets only on planned restart
        total_batches = 0
        retry_policy = RetryPolicy(max_attempts=2, base_delay=10.0, backoff_factor=1.0)
        # Sessions that fail every retry this run -- never re-queued until next run.
        exhausted_ids: set[str] = set()

        while True:
            completed_ids = self.repository.get_successfully_processed_ids()
            skip_ids = completed_ids | exhausted_ids
            batch = self.repository.get_pending_sessions(exclude_ids=skip_ids, limit=batch_size)

            self.logger.info(
                "[INFO] Completed so far: %d. Pulled %d pending session(s) from the DB queue.",
                len(completed_ids), len(batch),
            )

            if not batch:
                self.logger.info("[INFO] No pending sessions left. Archival complete.")
                break

            total_batches += 1
            self.logger.info(
                "[INFO] === BATCH %d: processing %d session(s) directly by URL ===",
                total_batches, len(batch),
            )

            for metadata in batch:
                sid = metadata.heidi_session_id

                # Exponential-backoff retry loop for this session
                while retry_policy.should_retry(sid):
                    retry_policy.record_attempt(sid)
                    retry_policy.sleep_before_retry(sid, self.logger)

                    global_ordinal += 1
                    success = self.process_one(global_ordinal, metadata)

                    if success:
                        sessions_this_cycle += 1

                        # --- Periodic Export & Anonymization ---
                        if global_ordinal > 0 and global_ordinal % 100 == 0:
                            self.logger.info(
                                "[INFO] Reached %d sessions. Triggering periodic export and anonymization...",
                                global_ordinal,
                            )
                            try:
                                from src.services.export_service import ExportService
                                from src.services.anonymize_service import AnonymizeService
                                ExportService(self.repository.db, self.exports_dir).export_all()
                                AnonymizeService().anonymize_csvs(self.exports_dir)
                                self.logger.info("[INFO] Periodic export and anonymization complete.")
                            except Exception as e:
                                self.logger.error("[ERROR] Periodic export/anonymization failed: %s", e)

                        break  # success -- move to next session
                    else:
                        if retry_policy.exhausted(sid):
                            self.logger.warning(
                                "[WARNING] Session %s exhausted all %d retries -- skipping permanently this run",
                                sid, retry_policy.max_attempts,
                            )
                            exhausted_ids.add(sid)
                        else:
                            self.logger.info(
                                "[RETRY] Session %s failed on attempt %d, will retry",
                                sid, retry_policy.attempts(sid),
                            )
                        global_ordinal -= 1  # revert ordinal if failed

                # Planned browser restart check (memory hygiene on long runs)
                if sessions_this_cycle >= self.restart_every:
                    self.logger.info(
                        "[INFO] Planned browser restart after %d sessions -- raising PlannedRestartSignal",
                        sessions_this_cycle,
                    )
                    raise PlannedRestartSignal(
                        f"Processed {sessions_this_cycle} sessions; clean restart requested."
                    )

            self.logger.info("[INFO] Batch %d complete.", total_batches)


    def process_one(self, ordinal: int, metadata: SessionMetadata) -> None:
        session_record, _ = self.repository.upsert_session_metadata(metadata)
        audit = self.repository.create_audit(session_record.id, status="started")
        screenshot_directory = self.screenshots.directory_for(ordinal)

        try:
            self.logger.info("[INFO] Loading session %s", ordinal)
            # open_session returns enriched metadata (with source_url captured from row click)
            metadata = self.discovery.open_session(metadata)

            # ——— Enrich metadata: scrape date/time from the now-open session page ———
            # The sidebar row may only show "Yesterday 02:28PM"; the detail view
            # always shows the full date. Do this BEFORE validation.
            if metadata.session_date is None:
                try:
                    detail_date = self.discovery.extract_date_from_open_session()
                    if detail_date:
                        metadata = metadata.model_copy(update={"session_date": detail_date})
                        self.logger.info("[INFO] Date enriched from session detail: %s", detail_date)
                except Exception as date_exc:
                    self.logger.warning("[WARNING] Could not enrich date from detail: %s", date_exc)

            overview_html = self.driver.page_source
            
            try:
                self.logger.info(
                    "[INSPECT] Before extraction: session_id=%s, patient_name=%s, overview HTML length=%d",
                    metadata.heidi_session_id,
                    metadata.patient_name,
                    len(overview_html)
                )
            except Exception as insp_exc:
                self.logger.warning("[WARNING] Inspect logging failed: %s", insp_exc)
                
            self.screenshots.save(self.driver, screenshot_directory, "overview")
            self.repository.save_artifact(
                session_id=session_record.id,
                artifact_type="overview",
                html_snapshot=overview_html,
                dom_snapshot="{}"
            )
            self.repository.db.commit()

            transcript = self.transcript_scraper.extract(screenshot_directory)
            self.repository.save_artifact(
                session_id=session_record.id,
                artifact_type="transcript",
                html_snapshot=transcript.html_snapshot,
                dom_snapshot=transcript.dom_snapshot,
                copy_text=transcript.copy_text,
                clipboard_text=transcript.clipboard_text,
                react_text=transcript.react_text,
                rendered_text=transcript.rendered_text,
                ocr_text=transcript.ocr_text,
            )
            self.repository.save_transcript(session_record.id, transcript.final_text)
            self.repository.db.commit()
            self.logger.info("[INFO] Transcript stored")

            note = self.note_scraper.extract(screenshot_directory)
            self.repository.save_artifact(
                session_id=session_record.id,
                artifact_type="note",
                html_snapshot=note.html_snapshot,
                dom_snapshot=note.dom_snapshot,
                copy_text=note.copy_text,
                clipboard_text=note.clipboard_text,
                react_text=note.react_text,
                rendered_text=note.rendered_text,
                ocr_text=note.ocr_text,
            )
            self.repository.save_soap_note(session_record.id, note.final_text)
            self.repository.db.commit()
            self.logger.info("[INFO] SOAP note stored")

            # CREATE ZIP PACKAGE
            self._create_zip_package(ordinal, metadata, overview_html, transcript, note, screenshot_directory)

            validation_result = self.validation.validate(metadata, transcript.final_text, note.final_text)

            if not validation_result.passed:
                error_message = "; ".join(validation_result.errors)
                self.repository.finish_audit(
                    audit,
                    status="failed",
                    validation_status=validation_result.status,
                    error_message=error_message,
                )
                self.repository.record_failed_extraction(metadata.heidi_session_id, error_message)
                self.repository.db.commit()
                self.logger.error("[ERROR] Validation failed for session %s: %s", ordinal, error_message)
                return

            transcript_hash = sha256_text(transcript.final_text)
            soap_hash = sha256_text(note.final_text)
            if self.repository.has_duplicate_content(session_record.id, transcript_hash, soap_hash):
                self.repository.finish_audit(
                    audit,
                    status="duplicate",
                    validation_status=validation_result.status,
                    error_message="Duplicate transcript and SOAP hashes detected.",
                )
                self.repository.remove_failed_extraction(metadata.heidi_session_id)
                self.repository.db.commit()
                self.checkpoint.update(ordinal)
                self.logger.warning("[WARNING] Duplicate session detected at ordinal %s — skipping (already stored)", ordinal)
                return True

            self.repository.finish_audit(audit, status="success", validation_status=validation_result.status)
            self.repository.remove_failed_extraction(metadata.heidi_session_id)
            self.repository.db.commit()
            # Write rich session pointer checkpoint — enables resume-from-exact-session on restart
            self.checkpoint.update_session_pointer(
                session_id=metadata.heidi_session_id,
                session_url=metadata.source_url,
                ordinal=ordinal,
            )
            self.logger.info("[INFO] Validation successful and ZIP packaged")
            
            try:
                memory_usage_mb = psutil.Process().memory_info().rss / (1024 * 1024)
                tab_count = len(self.driver.window_handles)
                self.logger.info(
                    "[METRICS] Session: %s | Memory: %.2f MB | Tabs: %d",
                    metadata.heidi_session_id, memory_usage_mb, tab_count
                )
            except Exception as metric_exc:
                self.logger.warning("[WARNING] Failed to log metrics: %s", metric_exc)
                
            return True
        except Exception as exc:
            exc_str = str(exc)
            # Detect Chrome tab crash — these are unrecoverable for the current session
            # but the browser itself may still be alive for the next one.
            if "tab crashed" in exc_str.lower() or "disconnected" in exc_str.lower():
                self.logger.error(
                    "[ERROR] Session %s: Chrome tab crashed. Raising BrowserCrashedError. Error: %s",
                    ordinal, exc_str.split(chr(10))[0],
                )
                self.repository.finish_audit(audit, status="failed", error_message=exc_str[:2000])
                self.repository.record_failed_extraction(metadata.heidi_session_id, exc_str[:500])
                self.repository.db.commit()
                raise BrowserCrashedError(exc_str)
            else:
                self.logger.error("[ERROR] Session %s failed: %s", ordinal, exc)
            self.repository.finish_audit(audit, status="failed", error_message=exc_str[:2000])
            self.repository.record_failed_extraction(metadata.heidi_session_id, exc_str[:500])
            self.repository.db.commit()
            return False

    def _create_zip_package(self, ordinal: int, metadata: SessionMetadata, overview_html: str, transcript, note, screenshot_directory: Path):
        try:
            zip_filename = self.exports_dir / f"session_{metadata.heidi_session_id}_{ordinal:06d}.zip"
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Metadata
                meta_dict = metadata.model_dump()
                if meta_dict.get('session_date'): meta_dict['session_date'] = str(meta_dict['session_date'])
                if meta_dict.get('session_time'): meta_dict['session_time'] = str(meta_dict['session_time'])
                zipf.writestr("metadata.json", json.dumps(meta_dict, indent=2))
                
                # Raw text files
                if transcript.final_text:
                    zipf.writestr("transcript.txt", transcript.final_text)
                if note.final_text:
                    zipf.writestr("soap.txt", note.final_text)
                
                # Raw HTML
                zipf.writestr("raw_overview.html", overview_html)
                zipf.writestr("raw_transcript.html", transcript.html_snapshot)
                zipf.writestr("raw_note.html", note.html_snapshot)

                # DOM Snapshots
                zipf.writestr("dom_snapshot_transcript.json", transcript.dom_snapshot)
                zipf.writestr("dom_snapshot_note.json", note.dom_snapshot)

                # Extracted Content JSON
                extracted_data = {
                    "transcript_versions": {
                        "copy": transcript.copy_text,
                        "clipboard": transcript.clipboard_text,
                        "dom": transcript.dom_text,
                        "react": transcript.react_text,
                        "rendered": transcript.rendered_text,
                        "ocr": transcript.ocr_text,
                    },
                    "note_versions": {
                        "copy": note.copy_text,
                        "clipboard": note.clipboard_text,
                        "dom": note.dom_text,
                        "react": note.react_text,
                        "rendered": note.rendered_text,
                        "ocr": note.ocr_text,
                    }
                }
                zipf.writestr("extraction_sources.json", json.dumps(extracted_data, indent=2))
                
                # Screenshots
                for file_path in screenshot_directory.glob("*.png"):
                    zipf.write(file_path, arcname=file_path.name)
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to create ZIP package for session {ordinal}: {e}")
