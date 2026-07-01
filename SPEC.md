# Heidi Health Scribe Archival System

## Objective

Build a production-grade archival platform that exports and preserves all historical Heidi Health Scribe sessions before account expiration.

The system must prioritize:

* Zero data loss
* High reliability
* Resume after interruption
* Complete auditability
* Structured storage
* Future analytics compatibility

This is not a proof-of-concept. Build for long-term archival of clinical documentation.

---

# Primary Goals

1. Archive every historical Scribe session.
2. Extract all available patient/session metadata.
3. Extract transcripts.
4. Extract SOAP notes.
5. Capture screenshots.
6. Store raw HTML snapshots.
7. Store data in SQL.
8. Generate audit reports.
9. Support resumable execution.
10. Prevent duplicate or corrupted records.

---

# Technology Requirements

## Language

Python 3.12+

## Libraries

* selenium
* chromedriver-autoinstaller
* sqlalchemy
* alembic
* pydantic
* tenacity
* rich
* pandas
* python-dotenv
* psycopg2-binary
* pyperclip

---

# Project Structure

```text
heidi_exporter/

├── src/
│
├── src/scraper/
│   ├── login.py
│   ├── navigator.py
│   ├── session_scraper.py
│   ├── transcript_scraper.py
│   └── note_scraper.py
│
├── src/database/
│   ├── db.py
│   ├── models.py
│   └── repository.py
│
├── src/services/
│   ├── checkpoint_service.py
│   ├── screenshot_service.py
│   ├── export_service.py
│   └── validation_service.py
│
├── src/utils/
│   ├── hashing.py
│   ├── logging.py
│   ├── retry.py
│   └── browser.py
│
├── exports/
├── screenshots/
├── logs/
├── checkpoints/
├── migrations/
│
├── .env
├── requirements.txt
├── README.md
└── main.py
```

---

# Environment Configuration

```env
HEIDI_EMAIL=

HEIDI_PASSWORD=

DATABASE_URL=

HEADLESS=false

MAX_RETRIES=5

SCREENSHOTS_ENABLED=true
```

---

# Browser Requirements

Automatically install ChromeDriver.

Use:

```python
chromedriver_autoinstaller.install()
```

Chrome must use persistent profile:

```text
chrome_profile/
```

This prevents repeated MFA prompts.

---

# Login Workflow

## Automatic Login

Read credentials from .env.

Attempt login automatically.

Wait for dashboard.

## Manual Login Fallback

If login fails:

Display:

Automatic login failed.

Please log in manually using the open browser.

Press ENTER when the Heidi dashboard is visible.

Continue after confirmation.

Do not terminate.

---

# Heidi Navigation

Current UI contains:

Left Sidebar:

* Scribe
* Evidence
* Tasks
* Comms

Center Area:

* Upcoming
* Past

Main Area:

* Context
* Transcript
* Note

Top-right copy buttons available for transcript and note.

---

# Session Discovery

Click:

Scribe

Then:

Past

Load all historical sessions.

Handle:

* Infinite scrolling
* Lazy loading
* Dynamic rendering
* Virtualized lists

Continue scrolling until no additional sessions appear.

---

# Metadata Collection

Collect:

* Session title
* Patient name
* Subtitle
* Date
* Time
* Language
* Duration
* Labels
* Tags
* Internal identifiers
* URL if available

Store metadata immediately.

Never wait until extraction completes.

---

# Session Processing

For each discovered session:

1. Open session.
2. Wait for rendering.
3. Save screenshot.
4. Save page HTML.
5. Extract transcript.
6. Extract SOAP note.
7. Validate.
8. Persist.
9. Update checkpoint.

---

# Transcript Extraction

Open Transcript tab.

Extraction priority:

1. Heidi copy button
2. Clipboard capture
3. DOM extraction
4. Rendered text extraction

Store complete transcript.

Preserve formatting.

Save screenshot.

---

# SOAP Note Extraction

Open Note tab.

Extraction priority:

1. Heidi copy button
2. Clipboard capture
3. DOM extraction
4. Rendered text extraction

Preserve formatting exactly.

Save screenshot.

---

# Screenshots

For every session create:

```text
screenshots/

session_0001/
├── overview.png
├── transcript.png
├── note.png

session_0002/
├── overview.png
├── transcript.png
├── note.png
```

Screenshots are mandatory.

---

# Raw HTML Archival

Store:

```python
driver.page_source
```

for:

* overview page
* transcript page
* note page

Compress if necessary.

---

# Database Design

## sessions

Fields:

* id
* heidi_session_id
* patient_name
* subtitle
* session_title
* session_date
* session_time
* language
* duration
* created_at
* updated_at

## transcripts

Fields:

* id
* session_id
* transcript_text
* sha256_hash
* created_at

## soap_notes

Fields:

* id
* session_id
* soap_text
* sha256_hash
* created_at

## raw_exports

Fields:

* id
* session_id
* html_snapshot
* screenshot_directory
* created_at

## scrape_audit

Fields:

* id
* session_id
* status
* validation_status
* retries_used
* error_message
* started_at
* completed_at

---

# Data Validation

Every session must pass:

## Transcript Validation

Transcript length > 0

## SOAP Validation

SOAP length > 0

## Metadata Validation

Patient name exists.

Date exists.

Session identifier exists.

---

# Hash Verification

Generate SHA256 hash for:

* transcript
* SOAP note

Store hashes.

Use hashes for duplicate detection.

---

# Duplicate Protection

Do not create duplicate records.

If duplicate detected:

Mark as duplicate in audit table.

Skip insertion.

---

# Retry System

Use Tenacity.

Retry:

* Click failures
* Clipboard failures
* Timeout exceptions
* Stale elements
* Rendering failures

Maximum retries:

5

Exponential backoff.

---

# Checkpoint System

Create:

```json
{
  "last_processed_session": 0
}
```

Update after every successful session.

If scraper crashes:

Resume from checkpoint.

Never restart from beginning.

---

# Logging

Use Rich logging.

Examples:

[INFO] Loading session 152

[INFO] Transcript extracted

[INFO] SOAP note extracted

[INFO] Validation successful

[WARNING] Transcript mismatch detected

[ERROR] SOAP extraction failed

---

# Export Requirements

Generate:

## SQL Dump

exports/heidi_dump.sql

## CSV

exports/sessions.csv

exports/transcripts.csv

exports/soap_notes.csv

## JSON

exports/all_sessions.json

## Audit Report

exports/audit_report.csv

---

# Audit Report Contents

* Total sessions discovered
* Total processed
* Success count
* Failure count
* Missing transcripts
* Missing SOAP notes
* Duplicate sessions
* Validation warnings
* Retry statistics

---

# Quality Requirements

Code must include:

* Type hints
* Pydantic models
* SQLAlchemy ORM
* Alembic migrations
* Structured logging
* Unit tests
* Modular architecture
* README

---

# Success Criteria

The system is considered complete only if:

1. Every historical Heidi Scribe session can be archived.
2. Transcript extraction is reliable.
3. SOAP note extraction is reliable.
4. Screenshots exist for every session.
5. Database records are validated.
6. Execution can resume after interruption.
7. Duplicate records are prevented.
8. Audit reports are generated.
9. Exports are generated.
10. No session is silently skipped.
