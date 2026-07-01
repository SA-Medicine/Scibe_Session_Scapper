from datetime import date
import logging

from src.database.db import build_engine, build_session_factory, create_tables
from src.database.models import TranscriptRecord
from src.database.repository import HeidiRepository
from src.database.schemas import SessionMetadata
from src.scraper.transcript_scraper import ExtractedContent
from src.services.archive_service import ArchiveService
from src.services.checkpoint_service import CheckpointService
from src.services.screenshot_service import ScreenshotService
from src.services.validation_service import ValidationService


class FakeDriver:
    page_source = "<html>overview</html>"


class FakeDiscovery:
    def open_session(self, metadata: SessionMetadata) -> SessionMetadata:
        return metadata


class FakeTranscriptScraper:
    def extract(self, screenshot_directory):
        return ExtractedContent(
            copy_text="Transcript text",
            clipboard_text="Transcript text",
            dom_text="Transcript text",
            react_text=None,
            rendered_text=None,
            ocr_text=None,
            final_text="Transcript text",
            html_snapshot="<html>transcript</html>",
            dom_snapshot="{}",
            screenshot_path=screenshot_directory / "transcript.png",
        )


class FailingNoteScraper:
    def extract(self, screenshot_directory):
        raise RuntimeError("note failed")


class EmptyDiscovery:
    def __init__(self) -> None:
        self.navigator = SimpleNamespace(open_past_sessions=lambda: None)
        self.reset_count = 0
        self.cursors: list[str | None] = []

    def _reset_session_list(self) -> None:
        self.reset_count += 1

    def discover_batch(self, batch_size, skip_ids, cursor_session_id=None):
        self.cursors.append(cursor_session_id)
        return []


class FakeCheckpoint:
    def __init__(self, cursor: str | None = None) -> None:
        self._cursor = cursor
        self.cleared = False

    def last_session_id(self):
        return self._cursor

    def update_session_pointer(self, session_id, session_url, ordinal):
        self.cleared = session_id is None
        self._cursor = session_id


class SimpleNamespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_archive_service_stores_transcript_before_later_failure(tmp_path) -> None:
    engine = build_engine("sqlite:///:memory:")
    create_tables(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as db:
        repo = HeidiRepository(db)
        archive = ArchiveService(
            driver=FakeDriver(),  # type: ignore[arg-type]
            discovery=FakeDiscovery(),  # type: ignore[arg-type]
            transcript_scraper=FakeTranscriptScraper(),  # type: ignore[arg-type]
            note_scraper=FailingNoteScraper(),  # type: ignore[arg-type]
            screenshots=ScreenshotService(tmp_path / "screenshots", enabled=False),
            checkpoint=CheckpointService(tmp_path / "checkpoints"),
            validation=ValidationService(),
            repository=repo,
            logger=logging.getLogger("test"),
        )
        archive.process_one(
            1,
            SessionMetadata(
                heidi_session_id="session-1",
                patient_name="Jane Doe",
                session_date=date(2026, 6, 11),
            ),
        )

        transcript = db.query(TranscriptRecord).one()
        assert transcript.raw_text == "Transcript text"


def test_archive_service_discards_stale_checkpoint_cursor(tmp_path) -> None:
    engine = build_engine("sqlite:///:memory:")
    create_tables(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as db:
        repo = HeidiRepository(db)
        session_record, _ = repo.upsert_session_metadata(
            SessionMetadata(heidi_session_id="heidi-completed", patient_name="Jane Doe", session_date=date(2026, 6, 11))
        )
        repo.finish_audit(repo.create_audit(session_record.id), status="success", validation_status="passed")

        discovery = EmptyDiscovery()
        checkpoint = FakeCheckpoint(cursor="heidi-stale")
        archive = ArchiveService(
            driver=FakeDriver(),  # type: ignore[arg-type]
            discovery=discovery,  # type: ignore[arg-type]
            transcript_scraper=FakeTranscriptScraper(),  # type: ignore[arg-type]
            note_scraper=FailingNoteScraper(),  # type: ignore[arg-type]
            screenshots=ScreenshotService(tmp_path / "screenshots", enabled=False),
            checkpoint=checkpoint,  # type: ignore[arg-type]
            validation=ValidationService(),
            repository=repo,
            logger=logging.getLogger("test"),
        )

        archive.process_sessions_batched(batch_size=1)

        assert discovery.cursors == [None]
        assert checkpoint.cleared

