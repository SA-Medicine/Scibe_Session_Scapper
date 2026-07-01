from __future__ import annotations

import os
from datetime import date, datetime, time, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint, LargeBinary, TypeDecorator, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from cryptography.fernet import Fernet
from pgvector.sqlalchemy import Vector

# Get encryption key from environment or use a static one for local dev (must be valid 32 url-safe base64-encoded bytes)
_ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode('utf-8'))
_fernet = Fernet(_ENCRYPTION_KEY.encode('utf-8'))

# Encryption disabled for testing phase. Mapped to Text to allow direct viewing in frontend.
EncryptedString = Text

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PatientRecord(Base):
    __tablename__ = "patients"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_name: Mapped[str] = mapped_column(EncryptedString, nullable=False) # Encrypted PHI
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    visit_count: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    sessions: Mapped[list["SessionRecord"]] = relationship(back_populates="patient")


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    heidi_session_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    patient_name_fallback: Mapped[str | None] = mapped_column(EncryptedString)
    subtitle: Mapped[str | None] = mapped_column(Text)
    session_title: Mapped[str | None] = mapped_column(String(500))
    session_date: Mapped[date | None] = mapped_column(Date)
    session_time: Mapped[time | None] = mapped_column(Time)
    language: Mapped[str | None] = mapped_column(String(100))
    duration: Mapped[str | None] = mapped_column(String(100))
    internal_identifier: Mapped[str | None] = mapped_column(String(255), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    patient: Mapped["PatientRecord | None"] = relationship(back_populates="sessions")
    transcript: Mapped["TranscriptRecord | None"] = relationship(back_populates="session", cascade="all, delete-orphan", uselist=False)
    soap_note: Mapped["NoteRecord | None"] = relationship(back_populates="session", cascade="all, delete-orphan", uselist=False)
    artifacts: Mapped[list["ArtifactRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    screenshots: Mapped[list["ScreenshotRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    audits: Mapped[list["AuditLogRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    ai_embeddings: Mapped[list["AiEmbeddingRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    tags: Mapped[list["TagRecord"]] = relationship(secondary="session_tags", back_populates="sessions")


class TranscriptRecord(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), unique=True, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(EncryptedString)  # Encrypted PHI
    clean_text: Mapped[str | None] = mapped_column(EncryptedString)
    word_count: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped["SessionRecord"] = relationship(back_populates="transcript")


class NoteRecord(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), unique=True, nullable=False)
    soap_note: Mapped[str | None] = mapped_column(EncryptedString)  # Encrypted PHI
    assessment: Mapped[str | None] = mapped_column(EncryptedString)
    plan: Mapped[str | None] = mapped_column(EncryptedString)
    summary: Mapped[str | None] = mapped_column(EncryptedString)
    hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped["SessionRecord"] = relationship(back_populates="soap_note")


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False) # transcript, note, overview
    raw_html: Mapped[str | None] = mapped_column(Text)
    dom_json: Mapped[str | None] = mapped_column(JSON)
    clipboard_capture: Mapped[str | None] = mapped_column(EncryptedString)
    rendered_text: Mapped[str | None] = mapped_column(EncryptedString)
    ocr_text: Mapped[str | None] = mapped_column(EncryptedString)
    copy_button_text: Mapped[str | None] = mapped_column(EncryptedString)
    react_state_text: Mapped[str | None] = mapped_column(EncryptedString)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped["SessionRecord"] = relationship(back_populates="artifacts")


class ScreenshotRecord(Base):
    __tablename__ = "screenshots"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    page_type: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped["SessionRecord"] = relationship(back_populates="screenshots")


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    validation_status: Mapped[str | None] = mapped_column(String(50))
    retries_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped["SessionRecord | None"] = relationship(back_populates="audits")


class FailedExtractionRecord(Base):
    __tablename__ = "failed_extractions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AiEmbeddingRecord(Base):
    __tablename__ = "ai_embeddings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50)) # transcript, summary, soap
    embedding: Mapped[list[float] | None] = mapped_column(Vector(3072)) # size depends on embedding model, 3072 for text-embedding-3-large
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped["SessionRecord"] = relationship(back_populates="ai_embeddings")


class TagRecord(Base):
    __tablename__ = "tags"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    sessions: Mapped[list["SessionRecord"]] = relationship(secondary="session_tags", back_populates="tags")


class SessionTag(Base):
    __tablename__ = "session_tags"
    
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), primary_key=True)


class ExportRecord(Base):
    __tablename__ = "exports"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    export_type: Mapped[str] = mapped_column(String(50), nullable=False) # csv, zip, json, sql
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
