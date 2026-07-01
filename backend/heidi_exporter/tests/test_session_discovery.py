from __future__ import annotations

import logging
from types import SimpleNamespace

from src.database.schemas import SessionMetadata
from src.scraper.session_scraper import SessionDiscovery


class FakeDriver:
    def execute_script(self, script: str, *args):
        if "window.innerWidth" in script:
            return 1240
        return [0, 0, 0]


class FakeRepository:
    def __init__(self) -> None:
        self.db = SimpleNamespace(commit=lambda: None)
        self.upserts: list[SessionMetadata] = []

    def upsert_session_metadata(self, metadata: SessionMetadata):
        self.upserts.append(metadata)
        return None, True


class ScriptedDiscovery(SessionDiscovery):
    def __init__(self, batches: list[list[SessionMetadata]]) -> None:
        super().__init__(FakeDriver(), None, FakeRepository(), logging.getLogger("test"))  # type: ignore[arg-type]
        self._batches = batches
        self._iteration = 0
        self.post_scroll_sleep_seconds = 0
        self.scroll_poll_attempts = 0
        self.scroll_poll_interval_seconds = 0

    def _candidate_elements(self):
        index = min(self._iteration, len(self._batches) - 1)
        return self._batches[index]

    def _metadata_from_element(self, element):
        return element

    def _scroll_session_list(self, row, pixels):
        self._iteration += 1
        return (100, 200, 300)

    def _reset_session_list(self) -> None:
        return None


def test_session_lane_excludes_sidebar_and_accepts_past_rows() -> None:
    discovery = SessionDiscovery(FakeDriver(), None, None, None)  # type: ignore[arg-type]

    sidebar_rect = {"x": 980, "width": 160, "height": 38}
    row_rect = {"x": 196, "width": 193, "height": 44}
    main_rect = {"x": 1000, "width": 600, "height": 44}

    assert not discovery._is_in_session_column(sidebar_rect)
    assert discovery._is_in_session_column(row_rect)
    assert not discovery._is_in_session_column(main_rect)
    assert discovery._looks_like_session_row("Confus, H/A\n8:02PM", row_rect)
    assert not discovery._looks_like_session_row("Scribe", row_rect)


def test_discover_batch_falls_back_when_cursor_is_not_seen() -> None:
    cursor = SessionMetadata(heidi_session_id="heidi-cursor", patient_name="Cursor Patient")
    skipped = SessionMetadata(heidi_session_id="heidi-skip", patient_name="Skipped Patient")
    discovered = SessionMetadata(heidi_session_id="heidi-new", patient_name="New Patient")

    discovery = ScriptedDiscovery([
        [skipped],
        [skipped],
        [discovered],
    ])
    discovery.cursor_fallback_stable_rounds = 1

    result = discovery.discover_batch(batch_size=1, skip_ids={"heidi-skip"}, cursor_session_id=cursor.heidi_session_id)

    assert [item.heidi_session_id for item in result] == ["heidi-new"]
    assert [item.heidi_session_id for item in discovery.repository.upserts] == ["heidi-new"]

