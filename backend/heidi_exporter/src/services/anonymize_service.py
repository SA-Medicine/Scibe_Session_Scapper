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
        
        # --- Setup Presidio ---
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        
        # Map each PHI type -> a Faker replacement
        self.operators = {
            "PERSON":       OperatorConfig("custom", {"lambda": lambda x: self.fake.name()}),
            "PHONE_NUMBER": OperatorConfig("custom", {"lambda": lambda x: self.fake.phone_number()}),
            "EMAIL_ADDRESS":OperatorConfig("custom", {"lambda": lambda x: self.fake.email()}),
            "LOCATION":     OperatorConfig("custom", {"lambda": lambda x: self.fake.city()}),
            "DATE_TIME":    OperatorConfig("custom", {"lambda": lambda x: str(self.fake.date())}),
            "AGE":          OperatorConfig("custom", {"lambda": lambda x: str(self.fake.random_int(18, 85))}),
            "URL":          OperatorConfig("replace",{"new_value": "[REDACTED-URL]"}),
        }

    def regex_cleanup(self, text: str) -> str:
        # Catch ages like "I am 34 years old" or "45-year-old"
        text = re.sub(r'\b(\d{1,3})[- ]?year[s]?[- ]?old\b', 
                      lambda m: f'{self.fake.random_int(18,85)}-year-old', text, flags=re.IGNORECASE)
        # Catch phone numbers
        text = re.sub(r'\b[6-9]\d{9}\b', lambda m: self.fake.numerify('##########'), text)
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
