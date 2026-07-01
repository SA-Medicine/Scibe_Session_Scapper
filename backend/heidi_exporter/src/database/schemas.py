from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field


class SessionMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    heidi_session_id: str
    patient_name: str | None = None
    subtitle: str | None = None
    session_title: str | None = None
    session_date: date | None = None
    session_time: time | None = None
    language: str | None = None
    duration: str | None = None
    labels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    internal_identifier: str | None = None
    source_url: str | None = None


class SessionPayload(BaseModel):
    metadata: SessionMetadata
    transcript_text: str
    soap_text: str
    overview_html: str
    transcript_html: str
    note_html: str
    screenshot_directory: str


class ValidationResult(BaseModel):
    passed: bool
    status: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

