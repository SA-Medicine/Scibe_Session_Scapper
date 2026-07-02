import json
import logging
import re
from pathlib import Path

import pandas as pd
from faker import Faker
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import TranscriptRecord, NoteRecord


class AnonymizeService:
    def __init__(self):
        self.fake = Faker('en_US')

        # Stable mapping so the SAME detected name always becomes the SAME label.
        # This lists patients clearly ("Patient 1", "Patient 2", ...) instead of
        # swapping in random fake names that look real and cause confusion.
        self._patient_map: dict[str, str] = {}

        # --- Setup Presidio ---
        # Presidio logs a WARNING for every non-English (es/it/pl) recognizer it
        # skips while loading its built-in library. Those are harmless noise for
        # our English-only pipeline, so quiet them to ERROR.
        logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

        # Map each PHI type -> a replacement.
        # PERSON is replaced with a consistent "Patient N" label (see _patient_label).
        self.operators = {
            "PERSON":       OperatorConfig("custom", {"lambda": self._patient_label}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "EMAIL_ADDRESS":OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "LOCATION":     OperatorConfig("replace", {"new_value": "[LOCATION]"}),
            "DATE_TIME":    OperatorConfig("custom",  {"lambda": lambda x: str(self.fake.date())}),
            "AGE":          OperatorConfig("custom",  {"lambda": lambda x: str(self.fake.random_int(18, 85))}),
            "URL":          OperatorConfig("replace", {"new_value": "[REDACTED-URL]"}),
        }

    def _patient_label(self, original: str) -> str:
        """Return a stable 'Patient N' label for a detected person name.

        The same name (case/space-insensitive) always maps to the same label, so
        every reference to a given patient reads consistently across the note and
        across sessions -- no confusion from random fake names.
        """
        key = re.sub(r"\s+", " ", (original or "").strip().lower())
        if not key:
            return "[PATIENT]"
        if key not in self._patient_map:
            self._patient_map[key] = f"Patient {len(self._patient_map) + 1}"
        return self._patient_map[key]

    def regex_cleanup(self, text: str) -> str:
        # Catch ages like "I am 34 years old" or "45-year-old"
        text = re.sub(r'\b(\d{1,3})[- ]?year[s]?[- ]?old\b',
                      lambda m: f'{self.fake.random_int(18,85)}-year-old', text, flags=re.IGNORECASE)
        # Catch phone numbers
        text = re.sub(r'\b[6-9]\d{9}\b', lambda m: "[PHONE]", text)
        # Catch dates like 12/05/1990
        text = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', lambda m: str(self.fake.date()), text)
        return text

    def anonymize_text(self, text: str) -> str:
        if not text:
            return text
        results = self.analyzer.analyze(
            text=text,
            language="en",
            entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS",
                      "LOCATION", "DATE_TIME", "AGE", "URL"]
        )
        cleaned = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=self.operators
        ).text
        return self.regex_cleanup(cleaned)

    def anonymize_database(self, db_session: Session, dry_run: bool = False) -> None:
        print(f"Anonymizing Transcripts in Database... (Dry Run: {dry_run})")
        transcripts = db_session.scalars(select(TranscriptRecord)).all()
        for t in transcripts:
            if t.clean_text:
                anon = self.anonymize_text(t.clean_text)
                if dry_run:
                    print(f"\n--- Dry Run Transcript {t.id} ---")
                    print(f"Original: {t.clean_text[:200]}...")
                    print(f"Anon:     {anon[:200]}...")
                t.clean_text = anon
            if t.raw_text:
                anon = self.anonymize_text(t.raw_text)
                t.raw_text = anon

        print(f"\nAnonymizing SOAP Notes in Database... (Dry Run: {dry_run})")
        notes = db_session.scalars(select(NoteRecord)).all()
        for n in notes:
            for field in ['soap_note', 'assessment', 'plan', 'summary']:
                val = getattr(n, field)
                if val:
                    anon = self.anonymize_text(val)
                    if dry_run:
                        print(f"\n--- Dry Run Note {n.id} Field: {field} ---")
                        print(f"Original: {val[:200]}...")
                        print(f"Anon:     {anon[:200]}...")
                    setattr(n, field, anon)

        if not dry_run:
            db_session.commit()
            print("\nDatabase Anonymization Committed.")
        else:
            db_session.rollback()
            print("\nDry Run complete. No changes written to the database.")

    def anonymize_csvs(self, exports_dir: Path) -> None:
        transcripts_path = exports_dir / "transcripts.csv"
        if transcripts_path.exists():
            print(f"Anonymizing {transcripts_path}...")
            df = pd.read_csv(transcripts_path)
            if 'clean_text' in df.columns:
                df['clean_text'] = df['clean_text'].apply(lambda x: self.anonymize_text(str(x)) if pd.notna(x) else x)
            if 'raw_text' in df.columns:
                df['raw_text'] = df['raw_text'].apply(lambda x: self.anonymize_text(str(x)) if pd.notna(x) else x)
            anon_path = str(transcripts_path).replace(".csv", "_anon.csv")
            df.to_csv(anon_path, index=False)
            print(f"Saved anonymized: {anon_path}")

        notes_path = exports_dir / "soap_notes.csv"
        if notes_path.exists():
            print(f"Anonymizing {notes_path}...")
            df = pd.read_csv(notes_path)
            for field in ['soap_note', 'assessment', 'plan', 'summary']:
                if field in df.columns:
                    df[field] = df[field].apply(lambda x: self.anonymize_text(str(x)) if pd.notna(x) else x)
            anon_path = str(notes_path).replace(".csv", "_anon.csv")
            df.to_csv(anon_path, index=False)
            print(f"Saved anonymized: {anon_path}")

        # Also sanitise the JSON export so it never ships un-anonymized PHI.
        self.anonymize_json(exports_dir)

    def anonymize_json(self, exports_dir: Path) -> None:
        """Rewrite all_sessions.json with anonymized text and NO raw HTML/DOM blobs.

        The raw JSON produced by ExportService contains decrypted transcripts,
        SOAP notes, patient names and full-page HTML snapshots -- i.e. live PHI.
        This scrubs every free-text field through the same anonymizer used for the
        database/CSVs and strips the raw_html / dom_json artifact blobs (which are
        impractical to anonymize and are already retained in the per-session zips).
        The cleaned result is written to BOTH all_sessions.json (so the primary
        export is safe) and all_sessions_anon.json.
        """
        json_path = exports_dir / "all_sessions.json"
        if not json_path.exists():
            return
        print(f"Anonymizing {json_path}...")
        try:
            with json_path.open("r", encoding="utf-8") as handle:
                sessions = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[WARN] Could not read {json_path}: {exc}")
            return

        text_fields = ("raw_text", "clean_text", "soap_note", "assessment", "plan", "summary")
        artifact_text_fields = (
            "clipboard_capture", "dom_text", "rendered_text", "ocr_text",
            "copy_button_text", "react_state_text",
        )

        def scrub(value):
            return self.anonymize_text(value) if isinstance(value, str) and value else value

        for session in sessions:
            # Patient identifiers straight on the session
            for key in ("patient_name_fallback", "subtitle", "session_title"):
                if session.get(key):
                    session[key] = scrub(session[key])

            for block_key in ("transcript", "soap_note"):
                block = session.get(block_key)
                if isinstance(block, dict):
                    for f in text_fields:
                        if f in block:
                            block[f] = scrub(block[f])

            for artifact in session.get("artifacts", []) or []:
                if not isinstance(artifact, dict):
                    continue
                for f in artifact_text_fields:
                    if f in artifact:
                        artifact[f] = scrub(artifact[f])
                # Strip un-anonymizable PHI blobs entirely.
                artifact.pop("raw_html", None)
                artifact.pop("dom_json", None)

        for out_name in ("all_sessions.json", "all_sessions_anon.json"):
            with (exports_dir / out_name).open("w", encoding="utf-8") as handle:
                json.dump(sessions, handle, indent=2, ensure_ascii=False)
        print("Saved anonymized JSON (all_sessions.json + all_sessions_anon.json)")
