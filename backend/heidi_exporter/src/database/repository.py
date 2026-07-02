from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from src.database.models import (
    AuditLogRecord,
    SessionRecord,
    NoteRecord,
    TranscriptRecord,
    ArtifactRecord,
    ScreenshotRecord,
    FailedExtractionRecord,
    utc_now,
)
from src.database.schemas import SessionMetadata
from src.utils.hashing import sha256_text


class HeidiRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_session_metadata(self, metadata: SessionMetadata) -> tuple[SessionRecord, bool]:
        existing = self.get_session_by_heidi_id(metadata.heidi_session_id)
        created = existing is None
        record = existing or SessionRecord(heidi_session_id=metadata.heidi_session_id)
        # Using patient_name_fallback as the encrypted patient name for Phase 2
        record.patient_name_fallback = metadata.patient_name
        record.subtitle = metadata.subtitle
        record.session_title = metadata.session_title
        record.session_date = metadata.session_date
        record.session_time = metadata.session_time
        record.language = metadata.language
        record.duration = metadata.duration
        record.internal_identifier = metadata.internal_identifier
        record.source_url = metadata.source_url
        record.updated_at = utc_now()
        self.db.add(record)
        self.db.flush()
        return record, created

    def get_session_by_heidi_id(self, heidi_session_id: str) -> SessionRecord | None:
        return self.db.scalar(select(SessionRecord).where(SessionRecord.heidi_session_id == heidi_session_id))

    def create_audit(self, session_id: int | None, status: str = "started") -> AuditLogRecord:
        audit = AuditLogRecord(session_id=session_id, status=status, started_at=utc_now())
        self.db.add(audit)
        self.db.flush()
        return audit

    def finish_audit(
        self,
        audit: AuditLogRecord,
        status: str,
        validation_status: str | None = None,
        retries_used: int = 0,
        error_message: str | None = None,
    ) -> AuditLogRecord:
        audit.status = status
        audit.validation_status = validation_status
        audit.retries_used = retries_used
        audit.error_message = error_message
        audit.completed_at = utc_now()
        self.db.add(audit)
        self.db.flush()
        return audit

    def record_failed_extraction(self, heidi_session_id: str, failure_reason: str):
        record = self.db.scalar(select(FailedExtractionRecord).where(FailedExtractionRecord.session_id == heidi_session_id))
        if record is None:
            record = FailedExtractionRecord(session_id=heidi_session_id, failure_reason=failure_reason, retry_count=0)
        else:
            record.failure_reason = failure_reason
            record.retry_count += 1
            record.last_attempt = utc_now()
        self.db.add(record)
        self.db.flush()

    def remove_failed_extraction(self, heidi_session_id: str):
        record = self.db.scalar(select(FailedExtractionRecord).where(FailedExtractionRecord.session_id == heidi_session_id))
        if record:
            self.db.delete(record)
            self.db.flush()

    def has_duplicate_content(self, session_id: int, transcript_hash: str, soap_hash: str) -> bool:
        transcript_duplicate = self.db.scalar(
            select(TranscriptRecord.id)
            .where(TranscriptRecord.sha256 == transcript_hash, TranscriptRecord.session_id != session_id)
        )
        soap_duplicate = self.db.scalar(
            select(NoteRecord.id)
            .where(NoteRecord.hash == soap_hash, NoteRecord.session_id != session_id)
        )
        return transcript_duplicate is not None and soap_duplicate is not None

    def save_transcript(self, session_id: int, transcript_text: str) -> TranscriptRecord:
        digest = sha256_text(transcript_text)
        record = self.db.scalar(select(TranscriptRecord).where(TranscriptRecord.session_id == session_id))
        if record is None:
            record = TranscriptRecord(session_id=session_id, raw_text=transcript_text, clean_text=transcript_text, sha256=digest)
        else:
            record.raw_text = transcript_text
            record.clean_text = transcript_text
            record.sha256 = digest
        self.db.add(record)
        self.db.flush()
        return record

    def save_soap_note(self, session_id: int, soap_text: str) -> NoteRecord:
        digest = sha256_text(soap_text)
        record = self.db.scalar(select(NoteRecord).where(NoteRecord.session_id == session_id))
        if record is None:
            record = NoteRecord(session_id=session_id, soap_note=soap_text, hash=digest)
        else:
            record.soap_note = soap_text
            record.hash = digest
        self.db.add(record)
        self.db.flush()
        return record

    def save_artifact(
        self,
        session_id: int,
        artifact_type: str,
        html_snapshot: str,
        dom_snapshot: str,
        copy_text: str | None = None,
        clipboard_text: str | None = None,
        dom_text: str | None = None,
        react_text: str | None = None,
        rendered_text: str | None = None,
        ocr_text: str | None = None,
    ) -> ArtifactRecord:
        record = self.db.scalar(
            select(ArtifactRecord).where(
                ArtifactRecord.session_id == session_id,
                ArtifactRecord.type == artifact_type,
            )
        )
        if record is None:
            record = ArtifactRecord(session_id=session_id, type=artifact_type)
        record.raw_html = html_snapshot
        record.dom_json = dom_snapshot if dom_snapshot else "{}"
        record.copy_button_text = copy_text
        record.clipboard_capture = clipboard_text
        record.dom_text = dom_text
        record.react_state_text = react_text
        record.rendered_text = rendered_text
        record.ocr_text = ocr_text
        self.db.add(record)
        self.db.flush()
        return record

    def scalar_count(self, statement: Select[tuple[int]]) -> int:
        return int(self.db.scalar(statement) or 0)

    def get_successfully_processed_ids(self) -> set[str]:
        """Return the set of heidi_session_ids that are definitively done.

        Includes both 'success' and 'duplicate' audit statuses.
        Any session whose ID is in this set will be skipped by the extractor.
        """
        rows = self.db.execute(
            select(SessionRecord.heidi_session_id)
            .join(AuditLogRecord, AuditLogRecord.session_id == SessionRecord.id)
            .where(AuditLogRecord.status.in_(["success", "duplicate"]))
        ).scalars().all()
        return set(rows)

    # ── DB-driven extraction queue ────────────────────────────────────────────

    def count_sessions(self) -> int:
        """Total number of discovered sessions currently in the database."""
        return int(self.db.scalar(select(func.count(SessionRecord.id))) or 0)

    def get_pending_sessions(
        self,
        exclude_ids: set[str] | None = None,
        limit: int | None = None,
    ) -> list[SessionMetadata]:
        """Return sessions discovered but not yet completed.

        Source of truth for the extraction loop once the one-time discovery scroll
        has finished: the extractor pulls the next pending sessions straight from
        the database and opens each directly by URL, so it never has to re-scroll
        the list to find where it left off.
        """
        exclude_ids = exclude_ids or set()
        stmt = (
            select(SessionRecord)
            .order_by(SessionRecord.session_date.desc().nullslast(), SessionRecord.id.asc())
        )
        pending: list[SessionMetadata] = []
        for record in self.db.execute(stmt).scalars():
            if record.heidi_session_id in exclude_ids:
                continue
            pending.append(
                SessionMetadata(
                    heidi_session_id=record.heidi_session_id,
                    patient_name=record.patient_name_fallback,
                    subtitle=record.subtitle,
                    session_title=record.session_title,
                    session_date=record.session_date,
                    session_time=record.session_time,
                    language=record.language,
                    duration=record.duration,
                    internal_identifier=record.internal_identifier,
                    source_url=record.source_url,
                )
            )
            if limit is not None and len(pending) >= limit:
                break
        return pending

    def get_url_prefix_template(self) -> str | None:
        """Return a URL prefix learned from any captured source_url.

        The prefix is everything up to the trailing session id, e.g.
        'https://scribe.heidihealth.com/sessions/'. Returns None if no session has
        a usable URL yet.
        """
        url = self.db.scalar(
            select(SessionRecord.source_url).where(SessionRecord.source_url.isnot(None)).limit(1)
        )
        if not url or "/" not in url:
            return None
        return url.rsplit("/", 1)[0] + "/"
