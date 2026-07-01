from __future__ import annotations

from src.database.schemas import SessionMetadata, ValidationResult


class ValidationService:
    def validate(self, metadata: SessionMetadata, transcript_text: str, soap_text: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not metadata.heidi_session_id.strip():
            errors.append("Session identifier is missing.")
        # Metadata fields: demoted to warnings — content (transcript/SOAP) is what matters
        if not metadata.patient_name or not metadata.patient_name.strip():
            warnings.append("Patient name is missing.")
        if metadata.session_date is None:
            warnings.append("Session date is missing.")
        # Content: empty transcript/SOAP is a warning (some sessions may only have one)
        if not transcript_text.strip():
            warnings.append("Transcript length is zero.")
        if not soap_text.strip():
            warnings.append("SOAP note length is zero.")

        if metadata.session_time is None:
            warnings.append("Session time is missing.")
        if not metadata.duration:
            warnings.append("Duration is missing.")

        if errors:
            return ValidationResult(passed=False, status="failed", warnings=warnings, errors=errors)
        if warnings:
            return ValidationResult(passed=True, status="passed_with_warnings", warnings=warnings, errors=[])
        return ValidationResult(passed=True, status="passed", warnings=[], errors=[])

