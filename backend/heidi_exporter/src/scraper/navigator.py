from __future__ import annotations

import logging
import time

from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.scraper.selenium_helpers import click_text
from src.utils.retry import selenium_retry

# Selectors that indicate the Past sessions list panel is already open and loaded.
# We look for clickable session-like rows in the left column.
_PAST_SESSION_INDICATORS = [
    (By.XPATH, "//*[contains(@class,'past') or contains(@data-testid,'past')]"),
    (By.XPATH, "//*[contains(normalize-space(.),'Past') and (@role='tab' or @role='button')]"),
]

# A broad selector that finds ANY session row element on screen (used for quick presence check).
_SESSION_ROW_QUICK_CHECK = (
    By.XPATH,
    (
        "//a[contains(@href,'session') or contains(@href,'scribe')]"
        " | //button[contains(@class,'session') or contains(@class,'visit')]"
        " | //*[@data-session-id]"
        " | //*[@data-testid and (contains(@data-testid,'session') or contains(@data-testid,'visit'))]"
    ),
)


class HeidiNavigator:
    def __init__(self, driver: WebDriver, logger: logging.Logger, max_retries: int = 5):
        self.driver = driver
        self.logger = logger
        self.max_retries = max_retries

    # ── Public API ──────────────────────────────────────────────────────────

    def open_past_sessions(self) -> None:
        """Navigate to the Past sessions list.

        Handles the common case where the Scribe/Past panel is *already* open:
        clicking "Scribe" again would *close* it (it's a toggle). We detect
        the current UI state and only click what's actually needed.
        """
        state = self._detect_panel_state()
        self.logger.info("[INFO] Panel state detected: %s", state)

        if state in ("past_visible", "scribe_open_wrong_tab"):
            # Scribe panel is open. It might be on Upcoming or Past.
            # Clicking 'Past' is safe and idempotent, so always do it to be sure.
            self.logger.info("[INFO] Scribe panel is open, ensuring 'Past' is selected")
            self._click_past()
            self._wait_for_past_sessions_list()
            return

        # state == "closed" — panel is hidden/closed, click Scribe to open it then Past.
        self._click_scribe()
        self._click_past()
        self._wait_for_past_sessions_list()

    def open_session_url(self, url: str) -> None:
        self.driver.get(url)
        self._wait_for_session_detail()

    def open_tab(self, label: str) -> None:
        try:
            lower_label = label.lower()
            translate_str = "translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"

            from src.scraper.selenium_helpers import wait_for_any, dismiss_toasts
            # Dismiss any modal/toast overlays BEFORE clicking the tab —
            # Radix UI upgrade dialogs have pointer-events:auto and block tab clicks.
            dismiss_toasts(self.driver)

            # Target specific interactive elements (buttons, tabs, links) to avoid clicking text inside the editor
            locators = [
                (By.XPATH, f"//button[{translate_str}='{lower_label}']"),
                (By.XPATH, f"//*[@role='tab' and {translate_str}='{lower_label}']"),
                (By.XPATH, f"//a[{translate_str}='{lower_label}']"),
                (By.XPATH, f"//button[contains({translate_str}, '{lower_label}')]"),
                (By.XPATH, f"//*[@role='tab' and contains({translate_str}, '{lower_label}')]"),
                (By.XPATH, f"//a[contains({translate_str}, '{lower_label}')]")
            ]

            el = wait_for_any(self.driver, locators, timeout=20)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            # Native click fires React synthetic events correctly.
            # Fall back to JS click only when a covering element blocks it.
            try:
                el.click()
            except Exception:
                self.logger.info("[INFO] Regular click intercepted for tab '%s', using JS click", label)
                self.driver.execute_script("arguments[0].click();", el)
            # Wait for a tab panel to become active instead of sleeping blindly
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[role='tabpanel']"))
                )
            except TimeoutException:
                pass  # Tab panel may render differently; continue anyway
        except TimeoutException:
            self.logger.warning("[WARNING] Could not find tab labeled %s", label)
            raise


    # ── State detection ─────────────────────────────────────────────────────

    def _detect_panel_state(self) -> str:
        """Return one of: 'past_visible' | 'scribe_open_wrong_tab' | 'closed'."""

        # Check if the Scribe panel is open by looking for the "Upcoming" or "Past" tabs
        try:
            tabs = self.driver.find_elements(
                By.XPATH,
                "//*[self::button or @role='tab' or @role='button']"
                "[contains(normalize-space(.), 'Upcoming') or contains(normalize-space(.), 'Past')]",
            )
            visible_tabs = [el for el in tabs if self._is_element_visible(el)]
            if visible_tabs:
                # Panel is open. We don't strictly need to distinguish between Past and Upcoming here,
                # because `open_past_sessions` will safely click "Past" either way.
                return "scribe_open_wrong_tab"
        except Exception:
            pass

        return "closed"

    def _is_element_visible(self, el) -> bool:
        try:
            rect = el.rect
            if not rect or rect.get("width", 0) < 4 or rect.get("height", 0) < 4:
                return False
            return el.is_displayed()
        except Exception:
            return False

    def _is_element_in_left_panel(self, el, right_boundary: float) -> bool:
        try:
            rect = el.rect
            if not rect:
                return False
            el_left = float(rect.get("x", 0))
            el_right = el_left + float(rect.get("width", 0))
            width = float(rect.get("width", 0))
            height = float(rect.get("height", 0))
            return (
                el_right <= right_boundary
                and width >= 60
                and height >= 20
                and el.is_displayed()
            )
        except Exception:
            return False

    # ── Click helpers ────────────────────────────────────────────────────────

    @selenium_retry()
    def _click_scribe(self) -> None:
        self.logger.info("[INFO] Opening Scribe")
        click_text(self.driver, "Scribe", timeout=30)
        # Short pause for the panel slide-in animation
        time.sleep(0.3)

        # Safety: if clicking Scribe accidentally closed the panel (it's a toggle),
        # the Upcoming/Past tabs will no longer be visible.  Detect and re-open.
        if not self._upcoming_or_past_tabs_visible():
            self.logger.info("[INFO] Scribe click closed the panel — re-opening")
            click_text(self.driver, "Scribe", timeout=15)
            time.sleep(0.3)

    @selenium_retry()
    def _click_past(self) -> None:
        self.logger.info("[INFO] Opening Past sessions")
        try:
            click_text(self.driver, "Past", timeout=15)
        except Exception as e:
            self.logger.info("[INFO] 'Past' tab not clickable (%s) — assuming already on Past sessions page", type(e).__name__)

    def _upcoming_or_past_tabs_visible(self) -> bool:
        """Return True if the Scribe sidebar currently shows the Upcoming/Past tabs."""
        try:
            tabs = self.driver.find_elements(
                By.XPATH,
                "//*[self::button or @role='tab' or @role='button']"
                "[contains(normalize-space(.), 'Upcoming') or contains(normalize-space(.), 'Past')]",
            )
            return any(self._is_element_visible(el) for el in tabs)
        except Exception:
            return False

    def _wait_for_past_sessions_list(self) -> None:
        # Explicit sleep to guarantee React unmounts the session detail page and renders the list route
        time.sleep(1.5)
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(_SESSION_ROW_QUICK_CHECK)
            )
        except TimeoutException:
            self.logger.info("[INFO] No session rows found in Past list (list might be empty)")

    def _wait_for_session_detail(self) -> None:
        WebDriverWait(self.driver, 30).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//*[self::button or self::a or @role='tab' or @role='button']"
                    "[contains(., 'Context') or contains(., 'Transcript') "
                    "or contains(., 'Note')]",
                )
            )
        )
        # No blind sleep — presence_of_element_located already confirms the area is rendered
