"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("heidi_session_id", sa.String(length=255), nullable=False),
        sa.Column("patient_name", sa.String(length=255), nullable=True),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("session_title", sa.String(length=500), nullable=True),
        sa.Column("session_date", sa.Date(), nullable=True),
        sa.Column("session_time", sa.Time(), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("duration", sa.String(length=100), nullable=True),
        sa.Column("labels_json", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("internal_identifier", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_heidi_session_id"), "sessions", ["heidi_session_id"], unique=True)
    op.create_index(op.f("ix_sessions_internal_identifier"), "sessions", ["internal_identifier"], unique=False)
    op.create_table(
        "scrape_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("validation_status", sa.String(length=50), nullable=True),
        sa.Column("retries_used", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scrape_audit_session_id"), "scrape_audit", ["session_id"], unique=False)
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(op.f("ix_transcripts_sha256_hash"), "transcripts", ["sha256_hash"], unique=False)
    op.create_table(
        "soap_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("soap_text", sa.Text(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(op.f("ix_soap_notes_sha256_hash"), "soap_notes", ["sha256_hash"], unique=False)
    op.create_table(
        "raw_exports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("page_type", sa.String(length=50), nullable=False),
        sa.Column("html_snapshot", sa.Text(), nullable=False),
        sa.Column("screenshot_directory", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "page_type", name="uq_raw_exports_session_page"),
    )


def downgrade() -> None:
    op.drop_table("raw_exports")
    op.drop_index(op.f("ix_soap_notes_sha256_hash"), table_name="soap_notes")
    op.drop_table("soap_notes")
    op.drop_index(op.f("ix_transcripts_sha256_hash"), table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_index(op.f("ix_scrape_audit_session_id"), table_name="scrape_audit")
    op.drop_table("scrape_audit")
    op.drop_index(op.f("ix_sessions_internal_identifier"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_heidi_session_id"), table_name="sessions")
    op.drop_table("sessions")

