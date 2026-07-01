import os
import json
import logging
from typing import Dict, Any

class AiService:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            self.logger.warning("[WARNING] OPENAI_API_KEY is not set. AI Enrichment will be skipped.")
            self.available = False
        else:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                self.available = True
            except ImportError:
                self.logger.warning("[WARNING] openai package not installed. Run `pip install openai`.")
                self.available = False

    def generate_clinical_enrichment(self, transcript_text: str, soap_text: str) -> Dict[str, Any]:
        """Generates structured clinical entities and summaries from the raw text."""
        if not self.available:
            return {}

        prompt = f"""
        You are a medical AI assistant. Analyze the following clinical session (Transcript and SOAP note).
        Extract and return a JSON object with the following fields:
        - "summary": A brief clinical summary (2-3 sentences).
        - "diagnoses": List of string diagnoses.
        - "medications": List of string medications mentioned.
        - "symptoms": List of string symptoms.
        - "procedures": List of string procedures.
        - "follow_ups": List of follow-up actions.
        - "action_items": List of action items for the provider.
        - "keywords": List of 5-10 key clinical search terms.

        Transcript:
        {transcript_text[:10000]}

        SOAP Note:
        {soap_text[:10000]}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o", # Used as a proxy for GPT-5.5 as requested, since 5.5 is not released
                messages=[{"role": "system", "content": "You are a clinical NLP engine."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            self.logger.error(f"[ERROR] AI clinical enrichment failed: {e}")
            return {}

    def generate_embedding(self, text: str) -> list[float] | None:
        """Generates text embeddings using text-embedding-3-large."""
        if not self.available or not text.strip():
            return None
        try:
            response = self.client.embeddings.create(
                model="text-embedding-3-large",
                input=text[:8000] # truncate to avoid token limits
            )
            return response.data[0].embedding
        except Exception as e:
            self.logger.error(f"[ERROR] AI embedding generation failed: {e}")
            return None
