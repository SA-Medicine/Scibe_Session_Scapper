from datetime import date

from src.database.db import build_engine, build_session_factory, create_tables
from src.database.repository import HeidiRepository
from src.database.schemas import SessionMetadata
from src.services.export_service import ExportService


def test_export_service_writes_required_files(tmp_path) -> None:
    engine = build_engine("sqlite:///:memory:")
    create_tables(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as db:
        repo = HeidiRepository(db)
        session, _ = repo.upsert_session_metadata(
            SessionMetadata(heidi_session_id="heidi-1", patient_name="Jane Doe", session_date=date(2026, 6, 11))
        )
        audit = repo.create_audit(session.id)
        repo.save_transcript(session.id, "Transcript")
        repo.save_soap_note(session.id, "SOAP")
        repo.save_raw_export(session.id, "overview", "<html></html>", "screenshots/session_0001")
        repo.finish_audit(audit, "success", "passed")
        db.commit()

        ExportService(db, tmp_path).export_all()

    assert (tmp_path / "heidi_dump.sql").exists()
    assert (tmp_path / "sessions.csv").exists()
    assert (tmp_path / "transcripts.csv").exists()
    assert (tmp_path / "soap_notes.csv").exists()
    assert (tmp_path / "all_sessions.json").exists()
    assert (tmp_path / "audit_report.csv").exists()

