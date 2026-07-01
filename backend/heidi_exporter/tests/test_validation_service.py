from datetime import date

from src.database.schemas import SessionMetadata
from src.services.validation_service import ValidationService


def test_validation_requires_metadata_transcript_and_soap() -> None:
    metadata = SessionMetadata(heidi_session_id="", patient_name=None, session_date=None)

    result = ValidationService().validate(metadata, "", "")

    assert not result.passed
    assert "Session identifier is missing." in result.errors
    assert "Patient name is missing." in result.errors
    assert "Session date is missing." in result.errors
    assert "Transcript length is zero." in result.errors
    assert "SOAP note length is zero." in result.errors


def test_validation_passes_with_optional_warnings() -> None:
    metadata = SessionMetadata(heidi_session_id="abc", patient_name="Jane Doe", session_date=date(2026, 6, 11))

    result = ValidationService().validate(metadata, "Transcript", "SOAP")

    assert result.passed
    assert result.status == "passed_with_warnings"

