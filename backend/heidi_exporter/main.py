from __future__ import annotations

import argparse
import shutil

from src.database.db import build_engine, build_session_factory, create_tables, session_scope
from src.database.models import Base
from src.database.repository import HeidiRepository
from src.scraper.login import HeidiLogin
from src.scraper.navigator import HeidiNavigator
from src.scraper.note_scraper import NoteScraper
from src.scraper.session_scraper import SessionDiscovery
from src.scraper.transcript_scraper import TranscriptScraper
from src.services.archive_service import ArchiveService
from src.services.checkpoint_service import CheckpointService
from src.services.export_service import ExportService
from src.services.screenshot_service import ScreenshotService
from src.services.validation_service import ValidationService
from src.utils.browser import create_driver
from src.utils.logging import configure_logging, get_logger
from src.utils.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive Heidi Health Scribe sessions.")
    parser.add_argument("--export-only", action="store_true", help="Generate exports from the existing database.")
    parser.add_argument("--discover-only", action="store_true", help="Discover and persist metadata without extraction.")
    parser.add_argument("--reset-archive", action="store_true", help="Clear database tables and checkpoint, then exit.")
    parser.add_argument("--anonymize-db", action="store_true", help="Anonymize PHI in the database transcripts and SOAP notes.")
    parser.add_argument("--anonymize-csvs", action="store_true", help="Anonymize PHI in the exported CSV files.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without committing changes (for --anonymize-db).")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        metavar="N",
        help="Process sessions in batches of N (default: 10). Skips already-completed sessions automatically.",
    )
    parser.add_argument(
        "--restart-every",
        type=int,
        default=75,
        metavar="N",
        help=(
            "Restart the Chrome browser after every N successfully processed sessions (default: 75). "
            "Prevents memory leaks during very long runs (25k+ sessions). "
            "Resume position is saved to checkpoint so no sessions are re-scraped."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings.load()
    
    # Clear cookies directory at every start
    if settings.cookies_dir.exists():
        shutil.rmtree(settings.cookies_dir)
        
    settings.ensure_directories()
    configure_logging(settings.logs_dir)
    logger = get_logger("heidi_exporter")

    engine = build_engine(settings.database_url)
    create_tables(engine)
    session_factory = build_session_factory(engine)

    if args.reset_archive:
        Base.metadata.drop_all(engine)
        create_tables(engine)
        checkpoint_svc = CheckpointService(settings.checkpoints_dir)
        checkpoint_svc.clear()
        logger.info("[INFO] Archive database and checkpoint reset")
        return

    if args.export_only:
        with session_scope(session_factory) as db:
            ExportService(db, settings.exports_dir).export_all()
        logger.info("[INFO] Exports generated")
        return

    if args.anonymize_db or args.anonymize_csvs:
        from src.services.anonymize_service import AnonymizeService
        logger.info("[INFO] Starting anonymization process...")
        anonymizer = AnonymizeService()
        
        if args.anonymize_db:
            with session_scope(session_factory) as db:
                anonymizer.anonymize_database(db, dry_run=args.dry_run)
            logger.info("[INFO] Database anonymization complete")
            
        if args.anonymize_csvs:
            anonymizer.anonymize_csvs(settings.exports_dir)
            logger.info("[INFO] CSV exports anonymization complete")
            
        return

    from src.exceptions import BrowserCrashedError
    from src.services.archive_service import PlannedRestartSignal
    
    while True:
        driver = create_driver(settings)
        try:
            HeidiLogin(driver, settings, logger).login()
            with session_scope(session_factory) as db:
                repository = HeidiRepository(db)
                navigator = HeidiNavigator(driver, logger, settings.max_retries)
                screenshots = ScreenshotService(settings.screenshots_dir, settings.screenshots_enabled)
                discovery = SessionDiscovery(driver, navigator, repository, logger)
                if args.discover_only:
                    sessions = discovery.discover_all()
                    logger.info("[INFO] Discovery complete — %d sessions found", len(sessions))
                    return
    
                archive = ArchiveService(
                    driver=driver,
                    discovery=discovery,
                    transcript_scraper=TranscriptScraper(driver, navigator, screenshots, logger, settings.max_retries),
                    note_scraper=NoteScraper(driver, navigator, screenshots, logger, settings.max_retries),
                    screenshots=screenshots,
                    checkpoint=CheckpointService(settings.checkpoints_dir),
                    validation=ValidationService(),
                    repository=repository,
                    logger=logger,
                    restart_every=args.restart_every,
                )
                archive.process_sessions_batched(batch_size=args.batch_size)
                
                # If we exit process_sessions_batched without raising BrowserCrashedError,
                # we are completely done.
                ExportService(db, settings.exports_dir).export_all()
                from src.services.anonymize_service import AnonymizeService
                AnonymizeService().anonymize_csvs(settings.exports_dir)
                logger.info("[INFO] Final archive export and anonymization complete")
                break
        except BrowserCrashedError as crash_exc:
            logger.error("[ERROR] BrowserCrashedError caught in main loop. Recreating driver...")
        except PlannedRestartSignal as restart_sig:
            logger.info("[INFO] PlannedRestartSignal received (%s). Recreating driver cleanly...", restart_sig)
            # Fall through to finally -> driver.quit() -> loop restart
            # The checkpoint already holds the last_session_id cursor, so the
            # new ArchiveService instance will resume from the exact right session.
        except Exception as main_exc:
            logger.error("[ERROR] Unexpected error in main loop: %s", main_exc)
            import sys
            sys.exit(1)
        finally:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
