from __future__ import annotations

import logging
import time
from pathlib import Path

import pyperclip
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from src.scraper.navigator import HeidiNavigator
from src.scraper.selenium_helpers import (
    browser_clipboard_text,
    click_best_copy_button,
    clear_clipboard,
    dismiss_toasts,
    fast_dom_text,
)
from src.scraper.transcript_scraper import ExtractedContent
from src.services.screenshot_service import ScreenshotService
from src.utils.retry import selenium_retry


class NoteScraper:
    def __init__(
        self,
        driver: WebDriver,
        navigator: HeidiNavigator,
        screenshots: ScreenshotService,
        logger: logging.Logger,
        max_retries: int = 3,
    ):
        self.driver = driver
        self.navigator = navigator
        self.screenshots = screenshots
        self.logger = logger
        self.max_retries = max_retries

    def extract(self, screenshot_directory: Path) -> ExtractedContent:
        clear_clipboard(self.driver)
        try:
            self.navigator.open_tab("SOAP Note")
        except TimeoutException:
            self.logger.info("[INFO] Note tab not found, assuming empty note.")
            return ExtractedContent(
                copy_text=None,
                clipboard_text=None,
                dom_text=None,
                react_text=None,
                rendered_text=None,
                ocr_text=None,
                final_text="",
                html_snapshot="<div class='error'>No note tab found</div>",
                dom_snapshot="{}",
                screenshot_path=Path("/dev/null")
            )

        # Wait for content stability — Heidi streams notes asynchronously.
        # 3 consecutive 500 ms checks with no DOM change = 1.5 s stable window.
        self.logger.info("[INFO] Waiting for SOAP Note content to stabilize...")
        stability_script = """
        const callback = arguments[arguments.length - 1];
        let previous = document.body.innerText;
        let stableCount = 0;
        const interval = setInterval(() => {
            const current = document.body.innerText;
            if (current === previous) {
                stableCount++;
            } else {
                stableCount = 0;
            }
            previous = current;
            if (stableCount >= 3) {
                clearInterval(interval);
                callback(true);
            }
        }, 500);
        """
        try:
            original_timeout = self.driver.timeouts.script
            self.driver.set_script_timeout(3)          # max 3 s (was 6 s)
            self.driver.execute_async_script(stability_script)
            self.driver.set_script_timeout(original_timeout)
        except Exception:
            self.logger.warning("[WARNING] Stability wait timed out, proceeding anyway")

        # Take screenshot for preservation
        screenshot_path = self.screenshots.save(self.driver, screenshot_directory, "note")

        # HTML snapshot (kept for debug purposes)
        html_snapshot = self.driver.page_source

        # ── Extraction — fastest first ─────────────────────────────────────
        #
        # Priority order:
        #   1. fast_dom_text   — single JS call, ~50 ms, most reliable
        #   2. copy button     — clicks UI button, writes to clipboard
        #   3. pyperclip/JS    — reads clipboard after copy button
        #
        # React state scan and rendered/visible_text are removed:
        #   - react_state always failed on Heidi's current Tiptap version
        #   - visible_text is too noisy (entire page body)

        dom_text: str | None = None
        copy_text: str | None = None
        clipboard_text: str | None = None

        # 1. Fast DOM read
        try:
            result = self._strip_ui_noise(fast_dom_text(self.driver, context="note"))
            if result:
                dom_text = result
                self.logger.info("[INFO] SOAP note extracted via fast DOM text")
        except Exception as e:
            self.logger.warning(f"[WARNING] SOAP DOM extraction failed: {e}")

        # 2 & 3. Copy button → clipboard (only if DOM came back empty)
        if not dom_text:
            try:
                captured = self._copy_button_text()
                copy_text = self._strip_ui_noise(captured)
                clipboard_text = self._strip_ui_noise(self._clipboard_text() or browser_clipboard_text(self.driver))
            except FileNotFoundError:
                pass
            except Exception as e:
                self.logger.warning(f"[WARNING] SOAP copy/clipboard extraction failed: {e}")

        # ── Determine final text ───────────────────────────────────────────
        if dom_text:
            final_text = dom_text
        elif clipboard_text:
            final_text = clipboard_text
        elif copy_text:
            final_text = copy_text
        else:
            final_text = ""
            self.logger.error("[ERROR] All SOAP note extraction methods failed.")

        if final_text:
            self.logger.info("[INFO] SOAP note extracted successfully")

        return ExtractedContent(
            copy_text=copy_text,
            clipboard_text=clipboard_text,
            dom_text=dom_text,
            react_text=None,
            rendered_text=None,
            ocr_text=None,
            final_text=final_text,
            html_snapshot=html_snapshot,
            dom_snapshot="{}",
            screenshot_path=screenshot_path
        )

    @selenium_retry()
    def _copy_button_text(self) -> str:
        captured = click_best_copy_button(self.driver, "note", timeout=5)
        if captured:
            return captured

        # Keyboard Copy Fallback
        self.logger.info("[INFO] Copy button failed, trying Keyboard Fallback (Ctrl+A, Ctrl+C)")
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys

            # Dismiss any toasts that may be covering the editor
            dismiss_toasts(self.driver)
            time.sleep(0.2)

            # Find an element to focus using JS click (avoids interception)
            editor = self.driver.find_element(By.CSS_SELECTOR, '.ProseMirror, [contenteditable="true"], [role="textbox"]')
            self.driver.execute_script("arguments[0].click();", editor)
            time.sleep(0.1)

            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
            time.sleep(0.1)
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('c').key_up(Keys.CONTROL).perform()
            time.sleep(0.3)

            current = self._clipboard_text() or browser_clipboard_text(self.driver)
            if current:
                return current
        except Exception as e:
            self.logger.warning(f"[WARNING] Keyboard copy fallback failed: {e}")

        return ""

    def _clipboard_text(self) -> str:
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""

    def _strip_ui_noise(self, value: str | None) -> str | None:
        if not value: return value
        lines = [line.rstrip() for line in value.splitlines()]
        blocked = {
            "context",
            "transcript",
            "note",
            "copy",
            "auto",
            "goldilocks",
            "write",
            "fill form",
            "explain",
            "create",
            "clinical considerations",
        }
        while lines and lines[0].strip().lower() in blocked:
            lines.pop(0)
        while lines and lines[-1].strip().lower() in blocked:
            lines.pop()
        return "\n".join(lines).strip()
