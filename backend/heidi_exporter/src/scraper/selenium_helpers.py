from __future__ import annotations

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pyperclip

def wait_for_any(driver: WebDriver, locators: list[tuple[str, str]], timeout: int = 10):
    """Wait until at least one of the locators is visible."""
    end_time = time.time() + timeout
    while time.time() < end_time:
        for by, locator in locators:
            try:
                el = driver.find_element(by, locator)
                if el.is_displayed():
                    return el
            except Exception:
                pass
        time.sleep(0.3)
    raise TimeoutException(f"None of the locators were found within {timeout}s.")

def find_first(driver: WebDriver, locators: list[tuple[str, str]]):
    """Find the first element that matches any of the locators."""
    for by, locator in locators:
        try:
            el = driver.find_element(by, locator)
            return el
        except Exception:
            pass
    return None

def click_text(driver: WebDriver, text: str, timeout: int = 10):
    """Wait for an element containing the specific text and click it."""
    from selenium.common.exceptions import ElementClickInterceptedException
    lower_text = text.lower()
    translate_str = "translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    clickable = "self::button or self::a or @role='button' or @role='tab' or @role='menuitem' or @role='link'"
    locators = [
        (By.XPATH, f"//*[{clickable}][{translate_str}='{lower_text}']"),
        (By.XPATH, f"//*[{clickable}][contains({translate_str}, '{lower_text}')]")
    ]
    el = wait_for_any(driver, locators, timeout=timeout)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    # Native click fires all browser and React synthetic events correctly.
    # Fall back to JS click only if a covering element intercepts it.
    try:
        el.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", el)
    return el

def browser_clipboard_text(driver: WebDriver) -> str:
    """Attempt to read clipboard using browser JS."""
    try:
        return driver.execute_script("return navigator.clipboard.readText();")
    except Exception:
        return ""

def visible_text(driver: WebDriver) -> str:
    """Get all visible text from the body."""
    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return ""

def best_content_text(driver: WebDriver) -> str:
    """Fallback text extraction."""
    return visible_text(driver)

def clear_clipboard(driver: WebDriver):
    """Clear clipboard via JS and pyperclip to prevent cross-contamination."""
    try:
        driver.execute_script("navigator.clipboard.writeText('');")
    except Exception:
        pass
    try:
        import pyperclip
        pyperclip.copy("")
    except Exception:
        pass

def dismiss_toasts(driver: WebDriver) -> None:
    """Remove all toast/notification overlays AND modal backdrops that can block clicks.

    Covers:
    - Sonner toasts (data-sonner-toast)
    - Radix UI dialog/popover overlays (fixed inset-0, data-state=open)
      e.g. the Heidi upgrade/trial modal that appears between sessions
    """
    try:
        driver.execute_script("""
            // Remove toast notifications
            const toasts = document.querySelectorAll(
                '[data-sonner-toast], [data-radix-toast-viewport], ' +
                '.sonner-toast, [class*="toast" i], [class*="notification" i]'
            );
            toasts.forEach(el => { try { el.remove(); } catch(e) {} });

            // Remove Radix modal backdrops / overlays that intercept pointer events.
            // These are the full-screen divs Heidi uses for its upgrade/trial dialogs.
            const overlays = document.querySelectorAll(
                '[data-state="open"][class*="fixed"][class*="inset-0"], ' +
                '[data-aria-hidden="true"][aria-hidden="true"][class*="fixed"], ' +
                '[data-radix-dialog-overlay], [data-radix-alert-dialog-overlay]'
            );
            overlays.forEach(el => { try { el.remove(); } catch(e) {} });
        """)
    except Exception:
        pass


def fast_dom_text(driver: WebDriver, context: str = "") -> str:
    """Fastest possible text extraction — single JS call, no element handles.

    Tries all known ProseMirror/Tiptap/Lexical selectors in one round-trip.
    The optional *context* hint ('transcript' | 'note' | '') narrows the search
    to the most relevant tab panel first before falling back to any editor.
    Returns the longest non-empty result found, or '' if nothing matches.
    """
    try:
        result = driver.execute_script("""
            const ctx = (arguments[0] || '').toLowerCase();

            // If we have a context (e.g. 'transcript', 'note'), try scoped query first
            if (ctx) {
                const scopeSelectors = [
                    '[data-testid*="' + ctx + '"] .ProseMirror',
                    '[aria-label*="' + ctx + '"] .ProseMirror',
                    '[aria-labelledby*="' + ctx + '"] .ProseMirror',
                    '[class*="' + ctx + '"] .ProseMirror',
                    '[role="tabpanel"] .ProseMirror',
                ];
                for (const sel of scopeSelectors) {
                    try {
                        const el = document.querySelector(sel);
                        if (el) {
                            const t = (el.innerText || el.textContent || '').trim();
                            if (t.length > 10) return t;
                        }
                    } catch(e) {}
                }

                // Transcript is a READ-ONLY timed display — not a contenteditable editor.
                // Find the tabpanel with TRANSCRIPT content, NOT the session sidebar.
                //
                // KEY INSIGHT: Transcript timestamps are recording OFFSETS that always
                // start at 0:xx (e.g. 0:00, 0:30, 1:45). Session sidebar times are real
                // clock times like 4:06PM, 5:27PM — never starting with 0.
                // So /\b0:\d{2}\b/ uniquely fingerprints the transcript panel.
                const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

                // Priority 1: explicit Heidi marker
                for (const panel of panels) {
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if (/transcript started/i.test(t)) return t;
                }

                // Priority 2: panel containing a zero-offset timestamp (0:xx)
                // This is the definitive fingerprint of the transcript read-out.
                for (const panel of panels) {
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if (/\b0:\d{2}\b/.test(t) && t.length > 10) return t;
                }

                // Priority 3: panel containing the 'Copy' button label
                // (The transcript panel has a Copy button; the session sidebar does not)
                for (const panel of panels) {
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if (/\bCopy\b/.test(t) && t.length > 10) return t;
                }

                // Priority 4: largest visible panel that has no MM/DD/YYYY session dates
                const sessionDateRe = /\b(0[1-9]|[12]\d|3[01])\/(0[1-9]|1[0-2])\/\d{4}\b/;
                let largest = '';
                for (const panel of panels) {
                    if (panel.offsetParent === null) continue;
                    const t = (panel.innerText || panel.textContent || '').trim();
                    if ((t.match(sessionDateRe) || []).length > 2) continue;
                    if (t.length > largest.length) largest = t;
                }
                if (largest.length > 10) return largest;

            }

            // Generic editor selectors — ordered most-to-least specific
            const genericSelectors = [
                '.tiptap.ProseMirror',
                'div.ProseMirror[contenteditable="true"]',
                'div.ProseMirror',
                'div[contenteditable="true"]',
                '[data-lexical-editor="true"]',
                '[role="textbox"]',
            ];
            let best = '';
            for (const sel of genericSelectors) {
                try {
                    const el = document.querySelector(sel);
                    if (el) {
                        const t = (el.innerText || el.textContent || '').trim();
                        if (t.length > best.length) best = t;
                    }
                } catch(e) {}
            }
            return best;
        """, context)
        return result or ""
    except Exception:
        return ""

def read_editor_dom_text(driver: WebDriver) -> str:
    """Read text directly from the visible ProseMirror/Tiptap editor in the DOM.

    This is the most reliable extraction method in headless Chrome because it
    doesn't depend on the clipboard or copy buttons.
    """
    return fast_dom_text(driver)

def click_best_copy_button(driver: WebDriver, context: str = "note", timeout: int = 5) -> str:
    """Find and click the most relevant copy button on the page.

    Skips buttons that are disabled. Falls back to a JavaScript click if a
    covering element intercepts the regular click. Returns the clipboard text
    after a successful click, or empty string if no usable button is found.
    """
    clear_clipboard(driver)
    locators = [
        (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'copy')]"),
        (By.CSS_SELECTOR, "button[aria-label*='Copy' i]"),
    ]

    # Collect all candidate buttons and filter out disabled ones
    candidates = []
    end_time = time.time() + timeout
    while time.time() < end_time and not candidates:
        for by, locator in locators:
            try:
                elements = driver.find_elements(by, locator)
                for el in elements:
                    try:
                        # Skip disabled buttons — they won't copy anything
                        if el.get_attribute("disabled") is not None:
                            continue
                        if not el.is_displayed():
                            continue
                        candidates.append(el)
                    except Exception:
                        continue
            except Exception:
                continue
        if not candidates:
            time.sleep(0.3)

    if not candidates:
        return ""

    btn = candidates[0]
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        # Native click is preferred; JS click as fallback for covered elements
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(0.3)
        return pyperclip.paste() or browser_clipboard_text(driver)
    except Exception:
        return ""
