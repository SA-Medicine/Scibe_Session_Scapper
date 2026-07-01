from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pyperclip
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver

from src.scraper.navigator import HeidiNavigator
from src.scraper.selenium_helpers import (
    browser_clipboard_text,
    click_best_copy_button,
    clear_clipboard,
    fast_dom_text,
)
from src.services.screenshot_service import ScreenshotService
from src.utils.retry import selenium_retry

@dataclass(frozen=True)
class ExtractedContent:
    copy_text: str | None
    clipboard_text: str | None
    dom_text: str | None
    react_text: str | None
    rendered_text: str | None
    ocr_text: str | None
    final_text: str
    html_snapshot: str
    dom_snapshot: str
    screenshot_path: Path

class TranscriptScraper:
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
            self.navigator.open_tab("Transcript")
        except TimeoutException:
            self.logger.info("[INFO] Transcript tab not found, assuming empty transcript.")
            return ExtractedContent(
                copy_text=None,
                clipboard_text=None,
                dom_text=None,
                react_text=None,
                rendered_text=None,
                ocr_text=None,
                final_text="",
                html_snapshot="<div class='error'>No transcript tab found</div>",
                dom_snapshot="{}",
                screenshot_path=Path("/dev/null")
            )

        # Wait for content stability — Heidi streams notes asynchronously.
        # 3 consecutive 500 ms checks with no DOM change = 1.5 s stable window.
        self.logger.info("[INFO] Waiting for transcript content to stabilize...")
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
        screenshot_path = self.screenshots.save(self.driver, screenshot_directory, "transcript")

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
            result = self._strip_ui_noise(fast_dom_text(self.driver, context="transcript"))
            if result:
                dom_text = result
                self.logger.info("[INFO] Transcript extracted via fast DOM text")
        except Exception as e:
            self.logger.warning(f"[WARNING] Transcript DOM extraction failed: {e}")

        # 2 & 3. Copy button → clipboard (only if DOM came back empty)
        if not dom_text:
            try:
                captured = self._copy_button_text()
                copy_text = self._strip_ui_noise(captured)
                clipboard_text = self._strip_ui_noise(self._clipboard_text() or browser_clipboard_text(self.driver))
            except FileNotFoundError:
                pass
            except Exception as e:
                self.logger.warning(f"[WARNING] Transcript copy/clipboard extraction failed: {e}")

        # ── Determine final text ───────────────────────────────────────────
        if dom_text:
            final_text = dom_text
        elif clipboard_text:
            final_text = clipboard_text
        elif copy_text:
            final_text = copy_text
        else:
            final_text = ""
            self.logger.error("[ERROR] All transcript extraction methods failed.")

        if final_text:
            self.logger.info("[INFO] Transcript extracted successfully")

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
        captured = click_best_copy_button(self.driver, "transcript", timeout=5)
        if captured:
            return captured

        # Fallback: read the transcript-specific tabpanel directly via JS.
        # The session sidebar (Past/Upcoming) is ALSO a tabpanel — must filter it out.
        # KEY: transcript offset-timestamps always start at 0:xx; session clock-times never do.
        self.logger.info("[INFO] Copy button failed, extracting transcript from tabpanel")
        try:
            result = self.driver.execute_script("""
                const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

                // Priority 1: explicit Heidi marker
                for (const panel of panels) {
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if (/transcript started/i.test(t)) return t;
                }
                // Priority 2: zero-offset timestamp fingerprint (0:00, 0:30 ...)
                // Session sidebar has 4:06PM, never 0:xx
                for (const panel of panels) {
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if (/\\b0:\\d{2}\\b/.test(t) && t.length > 10) return t;
                }
                // Priority 3: panel with 'Copy' button label
                for (const panel of panels) {
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if (/\\bCopy\\b/.test(t) && t.length > 10) return t;
                }
                // Priority 4: largest visible panel without session dates
                const dtRe = /\\b(0[1-9]|[12]\\d|3[01])\\/(0[1-9]|1[0-2])\\/\\d{4}\\b/;
                let largest = '';
                for (const panel of panels) {
                    if (panel.offsetParent === null) continue;
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if ((t.match(dtRe) || []).length > 2) continue;
                    if (t.length > largest.length) largest = t;
                }
                return largest;
            """)
            if result:
                return result
        except Exception as e:
            self.logger.warning(f"[WARNING] Tabpanel JS extraction failed: {e}")

        raise TimeoutException("Could not extract transcript text from any method")



    def _clipboard_text(self) -> str:
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""

    def _strip_ui_noise(self, value: str | None) -> str | None:
        """Strip navigation chrome and UI elements from extracted transcript text.

        Strategy:
        1. If "Transcript started" / "Transcript ended" markers are present, extract
           only the content between them (most precise).
        2. Otherwise, remove known navigation/UI lines from top and bottom.
        """
        import re
        if not value:
            return value

        # ── Strategy 1: extract between Heidi transcript boundary markers ──────
        # Heidi always wraps transcript content with these known strings.
        start_match = re.search(r'Transcript started[^\n]*', value, re.IGNORECASE)
        end_match = re.search(r'Transcript ended[^\n]*', value, re.IGNORECASE)
        if start_match:
            if end_match and end_match.start() > start_match.start():
                value = value[start_match.start():end_match.end()].strip()
            else:
                # No end marker — take everything from the start marker forward
                value = value[start_match.start():].strip()
            # Remove residual UI fragments within the transcript block
            ui_fragments = [
                r'Copy\s*$',
                r'^pause[Ii]con\s*$',
                r'Transcribing is paused.*',
                r'Resume Transcribing.*',
                r'Review your note before use.*',
                r'^Upgrade to.*',
                r'^Your trial has ended.*',
                r'^C\$\d+.*',
                r'^Annually.*',
                r'^Monthly.*',
            ]
            for pattern in ui_fragments:
                value = re.sub(pattern, '', value, flags=re.MULTILINE | re.IGNORECASE)
            # Collapse multiple blank lines
            value = re.sub(r'\n{3,}', '\n\n', value).strip()
            return value

        # ── Strategy 2: trim known nav/UI lines from top and bottom ───────────
        lines = [line.rstrip() for line in value.splitlines()]

        # Lines that are purely UI/navigation noise
        blocked_exact = {
            "context", "transcript", "note", "copy", "auto", "goldilocks",
            "write", "fill form", "explain", "create",
            "skip to main content", "skip to sessions list panel",
            "heidi", "new session", "scribe", "evidence", "tasks",
            "my library", "my templates", "my forms", "community",
            "templates", "team", "settings", "dictate history",
            "help", "notifications", "upcoming", "past",
            "tidy up", "add patient identifier", "transcribe",
            "review your note before use to ensure it accurately represents the visit",
            "heidi | your ai care partner for modern clinical practice",
        }
        blocked_prefix = (
            "skip to", "heidi |", "upgrade to", "your trial",
            "c$", "annually", "monthly", "billed", "includes:",
            "everything in", "view all plans", "close",
            "pauseicon", "transcribing is paused", "resume transcribing",
        )

        filtered = []
        for line in lines:
            lower = line.strip().lower()
            if lower in blocked_exact:
                continue
            if any(lower.startswith(p) for p in blocked_prefix):
                continue
            filtered.append(line)

        # Trim leading/trailing empty lines
        while filtered and not filtered[0].strip():
            filtered.pop(0)
        while filtered and not filtered[-1].strip():
            filtered.pop()

        return "\n".join(filtered).strip() or None
