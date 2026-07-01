from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import date, datetime, timedelta, time as dt_time
from urllib.parse import urlparse

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from src.database.repository import HeidiRepository
from src.database.schemas import SessionMetadata
from src.scraper.navigator import HeidiNavigator
from src.scraper.selenium_helpers import dismiss_toasts


SESSION_ROW_SELECTORS = [
    "[data-testid*='session' i]",
    "a[href*='session' i]",
    "a[href*='scribe' i]",
    "button",
    "[role='button']",
    "[class*='session' i]",
    "[class*='visit' i]",
]

SIDEBAR_OR_CONTROL_TEXT = {
    "scribe",
    "evidence",
    "tasks",
    "comms",
    "my templates",
    "my forms",
    "templates",
    "past", "upcoming", "scribe", "generate", "start", "stop", "pause", "resume",
    "search", "settings", "logout", "profile", "menu", "close", "back", "next",
    "today", "yesterday", "this week", "last week", "older", "new session"
}

DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b"
)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?:\s*(?:am|pm|a\.m\.|p\.m\.))?\b", re.IGNORECASE)
SESSION_LIST_SCROLL_SCRIPT = """
const row = arguments[0];
let el = row;
while (el && el !== document.body) {
  const style = window.getComputedStyle(el);
  const scrollable = /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 5;
  if (scrollable) {
    el.scrollTop += arguments[1];
    return [el.scrollTop, el.scrollHeight, el.clientHeight];
  }
  el = el.parentElement;
}
window.scrollBy(0, arguments[1]);
return [window.scrollY, document.body.scrollHeight, window.innerHeight];
"""
SESSION_LIST_RESET_SCRIPT = """
const row = arguments[0];
let el = row;
while (el && el !== document.body) {
  const style = window.getComputedStyle(el);
  const scrollable = /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 5;
  if (scrollable) {
    el.scrollTop = 0;
    return true;
  }
  el = el.parentElement;
}
window.scrollTo(0, 0);
return false;
"""
NEAREST_DATE_SCRIPT = """
const row = arguments[0];
const rowRect = row.getBoundingClientRect();
const dateRe = /(?:\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}|\\d{4}-\\d{1,2}-\\d{1,2}|\\d{1,2}\\s+[A-Za-z]{3,9}\\s+\\d{4}|[A-Za-z]{3,9}\\s+\\d{1,2},?\\s+\\d{4}|yesterday|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)/i;
let best = "";
let bestDistance = Infinity;
for (const el of document.querySelectorAll("div,span,p")) {
  const text = (el.innerText || el.textContent || "").trim();
  if (!dateRe.test(text) || text.length > 40) continue;
  const rect = el.getBoundingClientRect();
  const sameColumn = rect.left < rowRect.right && rect.right > rowRect.left;
  const above = rect.bottom <= rowRect.top + 2;
  if (!sameColumn || !above) continue;
  const distance = rowRect.top - rect.bottom;
  if (distance < bestDistance) {
    bestDistance = distance;
    best = text;
  }
}
return best;
"""


class SessionDiscovery:
    def __init__(
        self,
        driver: WebDriver,
        navigator: HeidiNavigator,
        repository: HeidiRepository,
        logger: logging.Logger,
    ):
        self.driver = driver
        self.navigator = navigator
        self.repository = repository
        self.logger = logger
        self.last_scroll_offset = 0
        self.post_scroll_sleep_seconds = 0.8
        self.scroll_poll_attempts = 10
        self.scroll_poll_interval_seconds = 0.2
        self.cursor_fallback_stable_rounds = 4
        self.zero_yield_scroll_abort_threshold = 10

    def discover_all(self) -> list[SessionMetadata]:
        self.navigator.open_past_sessions()
        discovered: dict[str, SessionMetadata] = {}
        stable_rounds = 0
        last_scroll_state: tuple[int, int, int] | None = None

        while stable_rounds < 4:
            before_count = len(discovered)
            candidates = self._candidate_elements()
            for element in candidates:
                metadata = self._metadata_from_element(element)
                if metadata is None:
                    continue
                if metadata.heidi_session_id not in discovered:
                    self.logger.info("[INFO] Discovered session %s", metadata.heidi_session_id)
                    self.repository.upsert_session_metadata(metadata)
                    discovered[metadata.heidi_session_id] = metadata
            self.repository.db.commit()

            scroll_state = self._scroll_session_list(candidates[0] if candidates else None, 700)
            time.sleep(self.post_scroll_sleep_seconds)
            if len(discovered) == before_count and scroll_state == last_scroll_state:
                stable_rounds += 1
            else:
                stable_rounds = 0
            last_scroll_state = scroll_state

        self._reset_session_list()
        self.logger.info("[INFO] Total sessions discovered: %s", len(discovered))
        return list(discovered.values())

    def discover_batch(
        self,
        batch_size: int,
        skip_ids: set[str],
        cursor_session_id: str | None = None,
    ) -> list[SessionMetadata]:
        """Scroll the Past Sessions list and collect up to `batch_size` new sessions.

        Sessions whose heidi_session_id is in `skip_ids` are ignored — they have
        already been successfully processed.

        Args:
            batch_size:        Max new sessions to return.
            skip_ids:          Session IDs already completed — will be skipped.
            cursor_session_id: If provided, skip all sessions encountered BEFORE
                               this ID is seen in the scroll. This allows resuming
                               exactly from the last successfully processed session
                               without re-scrolling all completed sessions.

        Returns fewer than `batch_size` items only when the list is fully exhausted.
        """
        found: dict[str, SessionMetadata] = {}  # new sessions for THIS batch
        all_seen_ids: set[str] = set(skip_ids)
        stable_rounds = 0
        last_scroll_state: tuple[int, int, int] | None = None

        # Cursor state: if a cursor is given, we skip until we see it.
        cursor_found = cursor_session_id is None  # True means "already past cursor"
        if cursor_session_id:
            self.logger.info(
                "[INFO] discover_batch: cursor mode — skipping sessions until '%s' is seen",
                cursor_session_id,
            )

        # Restore scroll state if we have one from a previous batch run
        if self.last_scroll_offset > 0:
            self.logger.info("[INFO] Restoring previous batch scroll offset: %d", self.last_scroll_offset)
            # Instantly set scrollTop instead of scrolling down smoothly
            self.driver.execute_script(
                "const row = arguments[0];"
                "let el = row; while(el && el !== document.body) { "
                "  const style = window.getComputedStyle(el); "
                "  if(/(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 5) { "
                "    el.scrollTop = arguments[1]; return; "
                "  } el = el.parentElement; "
                "} window.scrollTo(0, arguments[1]);",
                self._candidate_elements()[0] if self._candidate_elements() else None,
                self.last_scroll_offset
            )
            time.sleep(1.0)

        scroll_iterations = 0
        MAX_SCROLL_ITERATIONS = 10_000  # hard cap — prevents infinite loop on 25k+ lists
        consecutive_zero_yield_scrolls = 0
        last_visible_ids: tuple[str, ...] | None = None

        while stable_rounds < 8 and len(found) < batch_size:
            if scroll_iterations >= MAX_SCROLL_ITERATIONS:
                self.logger.warning(
                    "[WARNING] Reached max scroll iterations (%d). Stopping batch.",
                    MAX_SCROLL_ITERATIONS,
                )
                break

            scroll_iterations += 1
            if scroll_iterations % 10 == 0:
                self.logger.info(
                    "[INFO] Still scrolling Past sessions... "
                    "(scrolled %d times, found %d/%d, skipped %d seen, cursor_found=%s)",
                    scroll_iterations, len(found), batch_size,
                    len(all_seen_ids), cursor_found,
                )

            before_found = len(found)
            candidates = self._candidate_elements()
            current_visible_ids: list[str] = []

            for element in candidates:
                if len(found) >= batch_size:
                    break
                metadata = self._metadata_from_element(element)
                if metadata is None:
                    continue
                sid = metadata.heidi_session_id
                current_visible_ids.append(sid)

                # --- Cursor logic: skip everything until we see the cursor ID ---
                if not cursor_found:
                    if sid == cursor_session_id:
                        cursor_found = True
                        self.logger.info(
                            "[INFO] Cursor session '%s' found — resuming collection from next session",
                            cursor_session_id,
                        )
                    # Don't collect this session; it's before or at the cursor.
                    all_seen_ids.add(sid)
                    continue
                # ----------------------------------------------------------------

                if sid in all_seen_ids:
                    continue
                # Brand-new session not yet done
                all_seen_ids.add(sid)
                found[sid] = metadata
                self.repository.upsert_session_metadata(metadata)
                self.logger.info("[INFO] Batch candidate: %s", sid)

            self.repository.db.commit()

            if len(found) >= batch_size:
                break

            scroll_state = self._scroll_session_list(
                candidates[0] if candidates else None, 700
            )
            if scroll_state:
                self.last_scroll_offset = scroll_state[0]

            # Active wait for new nodes instead of blind sleep
            new_nodes_found = False
            for _ in range(self.scroll_poll_attempts):
                time.sleep(self.scroll_poll_interval_seconds)
                current_candidates = self._candidate_elements()
                if not current_candidates:
                    continue
                # See if any visible session ID is not in our seen list
                for c in current_candidates:
                    meta = self._metadata_from_element(c)
                    if meta and meta.heidi_session_id not in all_seen_ids:
                        new_nodes_found = True
                        break
                if new_nodes_found:
                    break
                    
            if not new_nodes_found:
                self.logger.info("[INFO] Scroll yielded no new candidates in active wait.")

            visible_ids = tuple(current_visible_ids)
            progress_made = (
                len(found) > before_found
                or scroll_state != last_scroll_state
                or visible_ids != last_visible_ids
                or new_nodes_found
            )

            if not progress_made:
                stable_rounds += 1
                consecutive_zero_yield_scrolls += 1
                
                if consecutive_zero_yield_scrolls >= self.zero_yield_scroll_abort_threshold:
                    self.logger.warning(
                        "[WARNING] Scroll stalled: 10 consecutive scrolls yielded 0 new candidates. "
                        "Assuming bottom of list reached or DOM is stuck. Aborting batch early."
                    )
                    break

                # Secondary confirmation: after a short stable window either move the
                # cursor forward or verify that the list really is exhausted.
                if stable_rounds == self.cursor_fallback_stable_rounds:
                    if cursor_session_id and not cursor_found:
                        self.logger.warning(
                            "[WARNING] Cursor '%s' not observed after %d stable rounds; switching to forward-only recovery",
                            cursor_session_id,
                            self.cursor_fallback_stable_rounds,
                        )
                        cursor_found = True
                        stable_rounds = 0
                    else:
                        at_bottom = self._is_scroll_at_bottom(candidates[0] if candidates else None)
                        if not at_bottom:
                            self.logger.info(
                                "[INFO] stable_rounds=%d but JS says NOT at bottom yet — resetting stable counter",
                                self.cursor_fallback_stable_rounds,
                            )
                            stable_rounds = 0  # reset; keep scrolling
            else:
                stable_rounds = 0
                consecutive_zero_yield_scrolls = 0
            last_scroll_state = scroll_state
            last_visible_ids = visible_ids

        self.logger.info("[INFO] Batch collected %d new sessions", len(found))
        return list(found.values())


    def open_session(self, metadata: SessionMetadata) -> SessionMetadata:
        """Navigate to a session and return the metadata, enriched with source_url if captured."""
        # Dismiss any modal overlays (e.g. Heidi upgrade dialog) before navigating.
        # Radix fixed backdrops with pointer-events:auto intercept all clicks if left open.
        dismiss_toasts(self.driver)
        if metadata.source_url:
            self.navigator.open_session_url(metadata.source_url)
            return metadata
        self.navigator.open_past_sessions()
        self._reset_session_list()
        for _ in range(60):
            dismiss_toasts(self.driver)  # re-dismiss on each scroll iteration
            candidates = self._candidate_elements()
            for element in candidates:
                candidate = self._metadata_from_element(element)
                if candidate and self._same_session(candidate, metadata):
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    try:
                        element.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(0.8)
                    # Capture the URL the browser navigated to and enrich metadata.
                    # This prevents future open_session calls from needing to re-scroll.
                    current_url = self.driver.current_url
                    if current_url and current_url != "about:blank" and "heidi" in current_url.lower():
                        metadata = metadata.model_copy(update={"source_url": current_url})
                        self.repository.upsert_session_metadata(metadata)
                        self.repository.db.commit()
                    return metadata
            self._scroll_session_list(candidates[0] if candidates else None, 500)
            time.sleep(0.4)
        title = metadata.session_title or metadata.patient_name or metadata.heidi_session_id
        raise TimeoutException(f"Could not find session row in Past list: {title}")

    def _candidate_elements(self) -> list[WebElement]:
        elements: list[WebElement] = []
        seen_ids: set[str] = set()

        # Cache viewport width once — avoids an execute_script call per element
        try:
            viewport_width = int(self.driver.execute_script(
                "return window.innerWidth || document.documentElement.clientWidth;"
            ))
        except Exception:
            viewport_width = 1920  # safe fallback

        # Combine all selectors into a single CSS query to avoid multiple implicit waits
        combined_selector = ", ".join(SESSION_ROW_SELECTORS)

        for element in self.driver.find_elements(By.CSS_SELECTOR, combined_selector):
            try:
                text = element.text.strip()
                rect = element.rect
                href = element.get_attribute('href')
                key = f"{text[:80]}:{href or ''}"
            except StaleElementReferenceException:
                continue

            if not text or len(text) < 4 or key in seen_ids:
                continue
            if not self._is_in_session_column(rect, viewport_width):
                continue
            if not self._looks_like_session_row(text, rect, href):
                continue

            seen_ids.add(key)
            elements.append(element)
        return elements

    def _metadata_from_element(self, element: WebElement) -> SessionMetadata | None:
        try:
            text = element.text.strip()
            href = element.get_attribute("href")
            rect = element.rect
            data_id = (
                element.get_attribute("data-session-id")
                or element.get_attribute("data-id")
                or element.get_attribute("id")
            )
        except StaleElementReferenceException:
            return None

        if not self._looks_like_session_row(text, rect, href):
            return None

        try:
            source_url = href or self._nearest_link(element)
            nearest_date = self._nearest_date_header(element)
        except Exception:
            source_url = href
            nearest_date = None

        heidi_id = data_id or self._id_from_url(source_url) or self._stable_text_id(text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        date_text = text
        if nearest_date:
            date_text = f"{nearest_date}\n{text}"
            heidi_id = data_id or self._id_from_url(source_url) or self._stable_text_id(date_text)
        parsed_date = self._parse_date(date_text)
        parsed_time = self._parse_time(text)

        title = self._clean_title(lines[0]) if lines else None
        patient_name = self._parse_patient(lines) or title
        subtitle = lines[1] if len(lines) > 1 else None

        return SessionMetadata(
            heidi_session_id=heidi_id,
            patient_name=patient_name,
            subtitle=subtitle,
            session_title=title,
            session_date=parsed_date,
            session_time=parsed_time,
            language=self._parse_label_value(lines, "Language"),
            duration=self._parse_duration(text),
            labels=self._parse_prefixed_list(lines, "Label"),
            tags=self._parse_prefixed_list(lines, "Tag"),
            internal_identifier=data_id,
            source_url=source_url,
        )

    def _same_session(self, left: SessionMetadata, right: SessionMetadata) -> bool:
        # 1. Exact ID match — always authoritative
        if left.heidi_session_id == right.heidi_session_id:
            return True

        # 2. Text-hash ID match by time only.
        #    Sessions discovered without a real URL get a text-hash ID
        #    (heidi_session_id starts with "text-"). Their title is often a
        #    relative date like "Yesterday 03:38PM" which changes the next day.
        #    Since the time is stable, treat time-only match as sufficient
        #    when at least one ID is a text-hash.
        either_is_text_hash = (
            left.heidi_session_id.startswith("text-")
            or right.heidi_session_id.startswith("text-")
        )
        if either_is_text_hash and left.session_time and left.session_time == right.session_time:
            # Times match; dates may differ because of relative-label staleness.
            # Accept if dates also match OR at least one date is missing.
            if (
                left.session_date == right.session_date
                or left.session_date is None
                or right.session_date is None
            ):
                return True

        # 3. For untitled sessions, time-only match is also accepted
        #    (original logic kept for sessions without any title).
        if left.session_time and left.session_time == right.session_time:
            if not left.session_title and not right.session_title:
                if left.session_date == right.session_date or not left.session_date or not right.session_date:
                    return True

        # 4. Full match: title + date + time (all must be non-None)
        return (
            left.session_title == right.session_title
            and left.session_date == right.session_date
            and left.session_time == right.session_time
            and left.session_title is not None
        )

    def _is_in_session_column(self, rect: dict[str, float], viewport_width: int = 0) -> bool:
        if not viewport_width:
            try:
                viewport_width = int(self.driver.execute_script(
                    "return window.innerWidth || document.documentElement.clientWidth;"
                ))
            except Exception:
                viewport_width = 1920
        left = float(rect.get("x", 0))

        # As long as the element starts in the left ~75% of the screen, we consider it.
        # This prevents picking up profile dropdowns on the far right.
        return left < (viewport_width * 0.75)

    def _looks_like_session_row(self, text: str, rect: dict[str, float], href: str | None = None) -> bool:
        normalized = " ".join(text.lower().split())
        if normalized in SIDEBAR_OR_CONTROL_TEXT:
            return False
        if any(control == normalized for control in SIDEBAR_OR_CONTROL_TEXT):
            return False
        if any(control in normalized for control in ("context transcript note", "copy", "create resume")):
            return False
        line_count = len([line for line in text.splitlines() if line.strip()])
        if line_count > 4:
            return False
        if href and any(part in href.lower() for part in ("session", "scribe", "encounter", "consult")):
            return True
        if TIME_RE.search(text):
            return True
        if "untitled session" in normalized:
            return True
        return False

    def _scroll_session_list(self, row: WebElement | None, pixels: int) -> tuple[int, int, int]:
        try:
            if row is None:
                values = self.driver.execute_script("window.scrollBy(0, arguments[0]); return [window.scrollY, document.body.scrollHeight, window.innerHeight];", pixels)
            else:
                values = self.driver.execute_script(SESSION_LIST_SCROLL_SCRIPT, row, pixels)
            return tuple(int(value) for value in values)
        except Exception:
            try:
                fresh_candidates = self._candidate_elements()
                if fresh_candidates:
                    values = self.driver.execute_script(SESSION_LIST_SCROLL_SCRIPT, fresh_candidates[0], pixels)
                    return tuple(int(value) for value in values)
            except Exception:
                pass
            return (0, 0, 0)

    def _reset_session_list(self) -> None:
        candidates = self._candidate_elements()
        if candidates:
            try:
                self.driver.execute_script(SESSION_LIST_RESET_SCRIPT, candidates[0])
            except Exception:
                self.driver.execute_script("window.scrollTo(0, 0);")
        else:
            self.driver.execute_script("window.scrollTo(0, 0);")

    def _is_scroll_at_bottom(self, row: WebElement | None) -> bool:
        """Return True if the scrollable session list container is at (or past) its bottom."""
        try:
            script = """
            const row = arguments[0];
            let el = row;
            while (el && el !== document.body) {
              const style = window.getComputedStyle(el);
              const scrollable = /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 5;
              if (scrollable) {
                return (el.scrollTop + el.clientHeight) >= (el.scrollHeight - 50);
              }
              el = el.parentElement;
            }
            return (window.scrollY + window.innerHeight) >= (document.body.scrollHeight - 50);
            """
            return bool(self.driver.execute_script(script, row))
        except Exception:
            return True  # assume bottom on error so we don't loop forever

    def _nearest_date_header(self, element: WebElement) -> str | None:
        try:
            text = self.driver.execute_script(NEAREST_DATE_SCRIPT, element)
        except Exception:
            return None
        return text.strip() if isinstance(text, str) and text.strip() else None

    def _nearest_link(self, element: WebElement) -> str | None:
        try:
            # Replaced element.find_element(By.XPATH) with execute_script to bypass
            # the global implicitly_wait(1). If an element lacked an 'a' tag, Selenium
            # was waiting 1 full second *per element* *per scroll iteration*, resulting
            # in 12-minute timeouts instead of 30-second timeouts.
            script = "const a = arguments[0].closest('a') || arguments[0].querySelector('a'); return a ? a.href : null;"
            link = self.driver.execute_script(script, element)
            return link if link else None
        except Exception:
            return None

    def _id_from_url(self, url: str | None) -> str | None:
        if not url:
            return None
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        if path_parts:
            return path_parts[-1][:255]
        return None

    def _stable_text_id(self, text: str) -> str:
        return "text-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def _clean_title(self, value: str) -> str:
        return re.sub(r"^\W+", "", value).strip() or value.strip()

    def _parse_patient(self, lines: list[str]) -> str | None:
        for line in lines:
            match = re.search(r"(?:patient|client)\s*:?\s*(.+)$", line, flags=re.I)
            if match:
                return match.group(1).strip()
        return self._clean_title(lines[0]) if lines else None

    def _parse_date(self, text: str) -> date | None:
        """Parse a date from text, including relative words like Yesterday/Today."""
        today = date.today()
        lower = text.lower().strip()

        # Handle relative/natural language dates first
        if lower.startswith("today"):
            return today
        if lower.startswith("yesterday"):
            return today - timedelta(days=1)
        # Handle weekday names ("Monday", "Tuesday", …) — assume last occurrence
        weekdays = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                    "friday": 4, "saturday": 5, "sunday": 6}
        for word, wday in weekdays.items():
            if lower.startswith(word):
                days_back = (today.weekday() - wday) % 7 or 7
                return today - timedelta(days=days_back)

        # Numeric / month-name patterns
        patterns = [
            r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b",
            r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b",
            r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b",
            r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            try:
                groups = match.groups()
                if pattern.startswith(r"\b(\d{4})"):
                    return date(int(groups[0]), int(groups[1]), int(groups[2]))
                if "/" in pattern:
                    year = int(groups[2])
                    if year < 100:
                        year += 2000
                    return date(year, int(groups[1]), int(groups[0]))
                value = match.group(0).replace(",", "")
                for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
            except ValueError:
                continue
        return None

    def _parse_time(self, text: str) -> dt_time | None:
        match = re.search(r"\b(\d{1,2}):(\d{2})\s*([AP]M)?\b", text, flags=re.I)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        suffix = (match.group(3) or "").lower()
        if suffix == "pm" and hour < 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
        try:
            return dt_time(hour=hour, minute=minute)
        except ValueError:
            return None

    def _parse_duration(self, text: str) -> str | None:
        match = re.search(r"\b(\d+\s*(?:h|hr|hrs|hour|hours|m|min|mins|minute|minutes)(?:\s+\d+\s*(?:m|min|mins))?)\b", text, re.I)
        return match.group(1).strip() if match else None

    def _parse_label_value(self, lines: list[str], label: str) -> str | None:
        for line in lines:
            match = re.search(rf"{label}\s*:?\s*(.+)$", line, flags=re.I)
            if match:
                return match.group(1).strip()
        return None

    def _parse_prefixed_list(self, lines: list[str], prefix: str) -> list[str]:
        value = self._parse_label_value(lines, prefix)
        if not value:
            return []
        return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]

    # ── Session detail date extraction ───────────────────────────────────────

    def extract_date_from_open_session(self) -> date | None:
        """Scrape the session date from the currently-open session detail page.

        Heidi renders the date in the session header once the session is open.
        We try multiple selectors/strategies so this works across UI versions.
        Returns a date object or None if nothing could be parsed.
        """
        # Strategy 1: data-testid attributes that Heidi may use for the date/time
        testid_selectors = [
            "[data-testid*='session-date' i]",
            "[data-testid*='session-time' i]",
            "[data-testid*='date' i]",
            "[data-testid*='timestamp' i]",
        ]
        for sel in testid_selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    text = (el.text or el.get_attribute("textContent") or "").strip()
                    if text:
                        parsed = self._parse_date(text)
                        if parsed:
                            return parsed
            except Exception:
                continue

        # Strategy 2: Scan common header/meta elements for date-like text
        header_script = """
        const selectors = [
            'header', '[class*=header]', '[class*=session-info]',
            '[class*=session-meta]', '[class*=session-header]',
            '[class*=overview]', 'time', '[datetime]'
        ];
        const dateRe = /(?:\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}|yesterday|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)/i;
        const results = [];
        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) {
                const t = (el.innerText || el.textContent || '').trim().slice(0, 120);
                if (dateRe.test(t)) results.push(t);
            }
        }
        // Also check <time datetime="..."> attributes
        for (const el of document.querySelectorAll('time[datetime]')) {
            const dt = el.getAttribute('datetime');
            if (dt) results.push(dt);
        }
        return results;
        """
        try:
            candidates = self.driver.execute_script(header_script) or []
            for text in candidates:
                parsed = self._parse_date(str(text))
                if parsed:
                    return parsed
        except Exception:
            pass

        # Strategy 3: Broad scan of all visible short text nodes near the top of page
        broad_script = """
        const dateRe = /(?:\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}|yesterday|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)/i;
        const results = [];
        const els = document.querySelectorAll('span, p, div, small, label');
        for (const el of els) {
            if (el.children.length > 2) continue;
            const t = (el.innerText || '').trim();
            if (t.length > 0 && t.length < 80 && dateRe.test(t)) {
                const rect = el.getBoundingClientRect();
                if (rect.top < window.innerHeight * 0.4) results.push(t);
            }
        }
        return results;
        """
        try:
            candidates = self.driver.execute_script(broad_script) or []
            for text in candidates:
                parsed = self._parse_date(str(text))
                if parsed:
                    return parsed
        except Exception:
            pass

        return None
