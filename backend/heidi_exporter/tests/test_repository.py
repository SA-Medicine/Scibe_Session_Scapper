from datetime import date

from src.database.db import build_engine, build_session_factory, create_tables
from src.database.models import SessionRecord
from src.database.repository import HeidiRepository
from src.database.schemas import SessionMetadata
from src.utils.hashing import sha256_text


def test_repository_upserts_metadata_and_detects_duplicate_content() -> None:
    engine = build_engine("sqlite:///:memory:")
    create_tables(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as db:
        repo = HeidiRepository(db)
        metadata = SessionMetadata(
            heidi_session_id="heidi-1",
            patient_name="Jane Doe",
            session_date=date(2026, 6, 11),
        )
        first, created = repo.upsert_session_metadata(metadata)
        second, created_again = repo.upsert_session_metadata(metadata)

        assert created
        assert not created_again
        assert first.id == second.id

        repo.save_transcript(first.id, "same transcript")
        repo.save_soap_note(first.id, "same soap")

        other, _ = repo.upsert_session_metadata(
            SessionMetadata(heidi_session_id="heidi-2", patient_name="John Doe", session_date=date(2026, 6, 12))
        )

        assert repo.has_duplicate_content(other.id, sha256_text("same transcript"), sha256_text("same soap"))


def test_repository_returns_completed_session_ids_from_audit_log() -> None:
    engine = build_engine("sqlite:///:memory:")
    create_tables(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as db:
        repo = HeidiRepository(db)

        success_session, _ = repo.upsert_session_metadata(
            SessionMetadata(heidi_session_id="heidi-success", patient_name="Jane Doe", session_date=date(2026, 6, 11))
        )
        duplicate_session, _ = repo.upsert_session_metadata(
            SessionMetadata(heidi_session_id="heidi-duplicate", patient_name="John Doe", session_date=date(2026, 6, 12))
        )
        failed_session, _ = repo.upsert_session_metadata(
            SessionMetadata(heidi_session_id="heidi-failed", patient_name="Foo Bar", session_date=date(2026, 6, 13))
        )

        repo.finish_audit(repo.create_audit(success_session.id), status="success", validation_status="passed")
        repo.finish_audit(repo.create_audit(duplicate_session.id), status="duplicate", validation_status="passed")
        repo.finish_audit(repo.create_audit(failed_session.id), status="failed", validation_status="failed")

        assert repo.get_successfully_processed_ids() == {"heidi-success", "heidi-duplicate"}

