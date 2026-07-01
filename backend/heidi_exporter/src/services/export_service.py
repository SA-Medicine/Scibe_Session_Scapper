from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.database.models import ArtifactRecord, AuditLogRecord, SessionRecord, NoteRecord, TranscriptRecord


class ExportService:
    def __init__(self, db: Session, exports_dir: Path):
        self.db = db
        self.exports_dir = exports_dir
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def export_all(self) -> None:
        self.export_csvs()
        self.export_json()
        self.export_sql_dump()
        self.export_audit_report()

    def export_csvs(self) -> None:
        for table_name, filename in (
            ("sessions", "sessions.csv"),
            ("transcripts", "transcripts.csv"),
            ("notes", "soap_notes.csv"),
            ("audit_logs", "audit_logs.csv"),
        ):
            frame = pd.read_sql_query(f"SELECT * FROM {table_name}", self.db.bind)
            frame.to_csv(self.exports_dir / filename, index=False)

    def export_json(self) -> None:
        sessions = self.db.scalars(
            select(SessionRecord)
            .options(
                selectinload(SessionRecord.transcript),
                selectinload(SessionRecord.soap_note),
                selectinload(SessionRecord.artifacts),
                selectinload(SessionRecord.audits),
                selectinload(SessionRecord.tags),
            )
            .order_by(SessionRecord.id)
        ).all()
        payload = [self._session_to_dict(session) for session in sessions]
        with (self.exports_dir / "all_sessions.json").open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)

    def export_sql_dump(self) -> None:
        path = self.exports_dir / "heidi_dump.sql"
        ordered_tables = [SessionRecord, TranscriptRecord, NoteRecord, ArtifactRecord, AuditLogRecord]
        with path.open("w", encoding="utf-8") as handle:
            handle.write("-- Heidi Health Scribe archival SQL dump\n")
            for model in ordered_tables:
                table = model.__table__
                rows = self.db.execute(select(model)).scalars().all()
                if not rows:
                    continue
                handle.write(f"\n-- {table.name}\n")
                columns = [column.name for column in table.columns]
                column_sql = ", ".join(columns)
                for row in rows:
                    values = ", ".join(self._sql_literal(getattr(row, column)) for column in columns)
                    handle.write(f"INSERT INTO {table.name} ({column_sql}) VALUES ({values});\n")

    def export_audit_report(self) -> None:
        total_sessions = self._count(SessionRecord.id)
        total_processed = self._count(AuditLogRecord.id)
        success_count = self._status_count("success")
        failure_count = self._status_count("failed")
        duplicate_count = self._status_count("duplicate")
        missing_transcripts = self.db.scalar(
            select(func.count(SessionRecord.id))
            .outerjoin(TranscriptRecord)
            .where(TranscriptRecord.id.is_(None))
        )
        missing_soap = self.db.scalar(
            select(func.count(SessionRecord.id))
            .outerjoin(NoteRecord)
            .where(NoteRecord.id.is_(None))
        )
        validation_warnings = self.db.scalar(
            select(func.count(AuditLogRecord.id)).where(AuditLogRecord.validation_status == "passed_with_warnings")
        )
        retry_sum = self.db.scalar(select(func.coalesce(func.sum(AuditLogRecord.retries_used), 0)))
        retry_max = self.db.scalar(select(func.coalesce(func.max(AuditLogRecord.retries_used), 0)))

        report = pd.DataFrame(
            [
                {"metric": "Total sessions discovered", "value": total_sessions},
                {"metric": "Total processed", "value": total_processed},
                {"metric": "Success count", "value": success_count},
                {"metric": "Failure count", "value": failure_count},
                {"metric": "Missing transcripts", "value": int(missing_transcripts or 0)},
                {"metric": "Missing SOAP notes", "value": int(missing_soap or 0)},
                {"metric": "Duplicate sessions", "value": duplicate_count},
                {"metric": "Validation warnings", "value": int(validation_warnings or 0)},
                {"metric": "Retry statistics total", "value": int(retry_sum or 0)},
                {"metric": "Retry statistics max", "value": int(retry_max or 0)},
            ]
        )
        report.to_csv(self.exports_dir / "audit_report.csv", index=False)

    def _session_to_dict(self, session: SessionRecord) -> dict[str, Any]:
        return {
            "id": session.id,
            "heidi_session_id": session.heidi_session_id,
            "patient_name_fallback": getattr(session, 'patient_name_fallback', None),
            "subtitle": session.subtitle,
            "session_title": session.session_title,
            "session_date": session.session_date,
            "session_time": session.session_time,
            "language": session.language,
            "duration": session.duration,
            "tags": [tag.name for tag in session.tags] if hasattr(session, 'tags') else [],
            "internal_identifier": session.internal_identifier,
            "source_url": session.source_url,
            "transcript": self._record_to_dict(session.transcript),
            "soap_note": self._record_to_dict(session.soap_note),
            "artifacts": [self._record_to_dict(record) for record in session.artifacts],
            "audits": [self._record_to_dict(record) for record in session.audits],
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def _record_to_dict(self, record: Any) -> dict[str, Any] | None:
        if record is None:
            return None
        return {column.name: getattr(record, column.name) for column in record.__table__.columns}

    def _count(self, column: Any) -> int:
        return int(self.db.scalar(select(func.count(column))) or 0)

    def _status_count(self, status: str) -> int:
        return int(self.db.scalar(select(func.count(AuditLogRecord.id)).where(AuditLogRecord.status == status)) or 0)

    def _json_default(self, value: Any) -> str:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        return str(value)

    def _sql_literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (datetime, date, time)):
            return "'" + value.isoformat().replace("'", "''") + "'"
        return "'" + str(value).replace("'", "''") + "'"

