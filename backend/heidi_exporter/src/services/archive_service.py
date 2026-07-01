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
        """Process all sessions in rolling batches of `batch_size`.

        Uses the database as the source of truth for which sessions are already done.
        On crash/restart, reads `last_session_id` from checkpoint and passes it to
        `discover_batch()` as a cursor so the scroll resumes from the last position
        instead of rescanning from the top.

        Raises:
            PlannedRestartSignal: After `restart_every` sessions to trigger a clean
                                  browser restart in main.py (prevents memory leaks).
            BrowserCrashedError:  On unrecoverable Chrome crashes.
        """
        self.discovery.navigator.open_past_sessions()
        self.discovery._reset_session_list()

        global_ordinal = 0
        total_batches = 0
        sessions_this_cycle = 0  # resets only on planned restart
        retry_policy = RetryPolicy(max_attempts=2, base_delay=10.0, backoff_factor=1.0)
        # exhausted_ids persists for the ENTIRE run so sessions that fail all retries
        # are never re-discovered and retried in subsequent batches of the same run.
        exhausted_ids: set[str] = set()

        # Load resume cursor from checkpoint — None on fresh runs
        cursor_session_id: str | None = self.checkpoint.last_session_id()
        if cursor_session_id:
            # Stale-cursor guard: if the DB is empty (e.g. user cleared it manually),
            # the cursor points to a session that no longer exists in any context.
            # Scrolling for it would loop forever. Detect this and start fresh.
            _precheck_completed = self.repository.get_successfully_processed_ids()
            if not _precheck_completed:
                self.logger.warning(
                    "[WARNING] Checkpoint has cursor '%s' but database has 0 completed sessions. "
                    "DB was likely cleared — discarding stale cursor and starting from the beginning.",
                    cursor_session_id,
                )
                cursor_session_id = None
                self.checkpoint.update_session_pointer(
                    session_id=None,  # type: ignore[arg-type]
                    session_url=None,
                    ordinal=0,
                )
            elif cursor_session_id not in _precheck_completed:
                self.logger.warning(
                    "[WARNING] Checkpoint cursor '%s' is not present in the durable completed-session set. "
                    "Discarding stale cursor and resuming from the beginning with DB-backed skip state.",
                    cursor_session_id,
                )
                cursor_session_id = None
                self.checkpoint.update_session_pointer(
                    session_id=None,  # type: ignore[arg-type]
                    session_url=None,
                    ordinal=0,
                )
            else:
                self.logger.info(
                    "[INFO] Resume cursor loaded: '%s' — will skip to this session before collecting",
                    cursor_session_id,
                )

        # Move initial navigation out of the batch loop so we don't reset the list 
        # to the top on every 10 sessions.
        try:
            self.discovery.navigator.open_past_sessions()
            self.discovery._reset_session_list()
        except Exception as nav_exc:
            self.logger.error(
                "[ERROR] Initial navigation failed: %s. Waiting 10s before retry...",
                str(nav_exc).split("\n")[0],
            )
            time.sleep(10)
            try:
                self.discovery.navigator.open_past_sessions()
                self.discovery._reset_session_list()
            except Exception as nav_exc2:
                self.logger.error(
                    "[ERROR] Initial navigation failed again after retry: %s. Aborting.",
                    str(nav_exc2).split("\n")[0],
                )
                return

        while True:
            completed_ids = self.repository.get_successfully_processed_ids()

            self.logger.info(
                "[INFO] Sessions completed so far: %d. Looking for next batch of %d...",
                len(completed_ids),
                batch_size,
            )

            # Re-open past sessions for the batch (process_one navigates away),
            # but DO NOT reset the list. We will restore scroll position inside discover_batch.
            try:
                self.discovery.navigator.open_past_sessions()
            except Exception as nav_exc:
                self.logger.error(
                    "[ERROR] Re-navigation failed: %s. Waiting 10s before retry...",
                    str(nav_exc).split("\n")[0],
                )
                time.sleep(10)
                try:
                    self.discovery.navigator.open_past_sessions()
                except Exception as nav_exc2:
                    self.logger.error(
                        "[ERROR] Re-navigation failed again after retry: %s. Giving up this iteration.",
                        str(nav_exc2).split("\n")[0],
                    )
                    break

            skip_ids = completed_ids | exhausted_ids
            batch = self.discovery.discover_batch(
                batch_size,
                skip_ids,
                cursor_session_id=cursor_session_id,
            )
            # After first batch, clear the cursor — subsequent batches scroll forward naturally
            cursor_session_id = None

            if not batch:
                self.logger.info("[INFO] No new sessions found. Archival complete.")
                break

            total_batches += 1
            self.logger.info(
                "[INFO] === BATCH %d: processing %d sessions ===",
                total_batches,
                len(batch),
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
                            self.logger.info("[INFO] Reached %d sessions. Triggering periodic export and anonymization...", global_ordinal)
                            try:
                                from src.services.export_service import ExportService
                                from src.services.anonymize_service import AnonymizeService
                                ExportService(self.repository.db, self.exports_dir).export_all()
                                AnonymizeService().anonymize_csvs(self.exports_dir)
                                self.logger.info("[INFO] Periodic export and anonymization complete.")
                            except Exception as e:
                                self.logger.error("[ERROR] Periodic export/anonymization failed: %s", e)
                                
                        break  # success — move to next session
                    else:
                        if retry_policy.exhausted(sid):
                            self.logger.warning(
                                "[WARNING] Session %s exhausted all %d retries — skipping permanently this run",
                                sid, retry_policy.max_attempts,
                            )
                            exhausted_ids.add(sid)
                        else:
                            self.logger.info(
                                "[RETRY] Session %s failed on attempt %d, will retry",
                                sid, retry_policy.attempts(sid),
                            )
                        global_ordinal -= 1  # revert ordinal if failed

                # Planned browser restart check
                if sessions_this_cycle >= self.restart_every:
                    self.logger.info(
                        "[INFO] Planned browser restart after %d sessions — raising PlannedRestartSignal",
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
