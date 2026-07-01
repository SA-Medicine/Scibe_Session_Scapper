# Heidi Health Scribe Archival System

Production-oriented archival tool for exporting historical Heidi Health Scribe sessions before account expiration.

## Setup

1. Install Python 3.12 or newer.
2. From this directory, install dependencies:

```bash
pip install -r requirements.txt
```

3. Fill in `.env`.

```env
HEIDI_EMAIL=
HEIDI_PASSWORD=
DATABASE_URL=sqlite:///heidi_archive.db
HEADLESS=false
MAX_RETRIES=5
SCREENSHOTS_ENABLED=true
HEIDI_BASE_URL=https://scribe.heidihealth.com
```

For PostgreSQL, set `DATABASE_URL` to a SQLAlchemy URL such as:

```env
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/heidi_archive
```

## Run

```bash
python main.py
```

The first run opens Chrome with the persistent profile in `chrome_profile/`. The automatic login starts at `https://scribe.heidihealth.com`, enters the email, clicks Continue, waits for Heidi's password page, enters the password, and clicks Continue again. If automatic login fails or MFA is required, log in manually in the browser and press ENTER in the terminal once the Heidi dashboard is visible.

Useful modes:

```bash
python main.py --discover-only
python main.py --export-only
python main.py --reset-archive
```

Use `--reset-archive` after a bad test run to clear database rows and the checkpoint before scraping again.

## Outputs

- Screenshots: `screenshots/session_0001/overview.png`, `transcript.png`, `note.png`
- Checkpoint: `checkpoints/checkpoint.json`
- Logs: `logs/heidi_exporter.log`
- SQL database: configured by `DATABASE_URL`
- Exports:
  - `exports/heidi_dump.sql`
  - `exports/sessions.csv`
  - `exports/transcripts.csv`
  - `exports/soap_notes.csv`
  - `exports/all_sessions.json`
  - `exports/audit_report.csv`

## Reliability Features

- Metadata is persisted immediately during discovery.
- Transcript and SOAP extraction use copy button, clipboard, DOM, then rendered text fallbacks.
- Every processed session gets screenshots and raw HTML snapshots.
- Validation blocks empty transcript/SOAP records and missing required metadata.
- SHA256 hashes are stored for transcripts and SOAP notes.
- Duplicate transcript and SOAP hash pairs are marked in `scrape_audit` and skipped.
- Checkpointing resumes from the last successful session.
- Failures are audited rather than silently skipped.
- Chrome keeps a persistent profile in `chrome_profile/`, and the app also saves Heidi cookies in `cookies/heidi_cookies.json` after a successful login.

## Migrations

The repository includes Alembic configuration and an initial schema migration:

```bash
alembic upgrade head
```

`main.py` also calls SQLAlchemy `create_all()` so local SQLite runs are straightforward.
