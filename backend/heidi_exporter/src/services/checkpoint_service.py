from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class CheckpointService:
    """Persists scraping progress so that a restart resumes from the last known session.

    Checkpoint schema::

        {
          "last_processed_ordinal": 512,
          "last_session_id": "abc123",
          "last_session_url": "https://scribe.heidihealth.com/sessions/abc123",
          "total_processed": 512,
          "last_updated": "2026-06-25T20:00:00Z",
          "run_started": "2026-06-25T15:00:00Z"
        }
    """

    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.checkpoint_dir / "checkpoint.json"
        self._run_started: str = datetime.now(timezone.utc).isoformat()

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            # Back-compat: old checkpoints only had last_processed_session
            return {
                "last_processed_ordinal": int(
                    data.get("last_processed_session",
                             data.get("last_processed_ordinal", 0))
                ),
                "last_session_id": data.get("last_session_id"),
                "last_session_url": data.get("last_session_url"),
                "total_processed": int(data.get("total_processed", 0)),
                "last_updated": data.get("last_updated"),
                "run_started": data.get("run_started"),
            }
        except (json.JSONDecodeError, ValueError):
            return self._empty()

    def last_session_id(self) -> str | None:
        return self.load().get("last_session_id")

    def last_session_url(self) -> str | None:
        return self.load().get("last_session_url")

    # ── Compatibility shim ────────────────────────────────────────────────────

    def should_skip(self, ordinal: int) -> bool:
        return ordinal <= self.load()["last_processed_ordinal"]

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, ordinal: int) -> None:
        """Legacy-compatible update (ordinal only). Prefer update_session_pointer."""
        self._write(ordinal=ordinal)

    def update_session_pointer(
        self,
        session_id: str | None,
        session_url: str | None,
        ordinal: int,
    ) -> None:
        """Atomically persist the full session pointer after a successful extraction.
        Pass session_id=None to explicitly clear the cursor (e.g. after DB reset).
        """
        self._write(
            ordinal=ordinal,
            session_id=session_id,
            session_url=session_url,
            clear_cursor=(session_id is None),
        )

    def clear(self) -> None:
        """Fully reset the checkpoint (ordinal + cursor). Use after a DB wipe."""
        self._write(ordinal=0, session_id=None, session_url=None, clear_cursor=True)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _empty(self) -> dict:
        return {
            "last_processed_ordinal": 0,
            "last_session_id": None,
            "last_session_url": None,
            "total_processed": 0,
            "last_updated": None,
            "run_started": None,
        }

    def _write(
        self,
        ordinal: int,
        session_id: str | None = None,
        session_url: str | None = None,
        clear_cursor: bool = False,
    ) -> None:
        existing = self.load()
        data = {
            "last_processed_ordinal": ordinal,
            # When clear_cursor=True, explicitly set to None (DB was reset).
            # Otherwise, keep the existing value when no new one is provided.
            "last_session_id": None if clear_cursor else (session_id or existing.get("last_session_id")),
            "last_session_url": None if clear_cursor else (session_url or existing.get("last_session_url")),
            "total_processed": ordinal,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "run_started": existing.get("run_started") or self._run_started,
        }
        temp_path = self.path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        temp_path.replace(self.path)

