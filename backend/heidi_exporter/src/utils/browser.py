from __future__ import annotations

import time
from pathlib import Path

import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from src.utils.settings import Settings

# Sites that the scraper interacts with — clipboard permission granted for all of them.
_CLIPBOARD_ALLOWED_ORIGINS = [
    "https://scribe.heidihealth.com",
    "https://app.heidihealth.com",
    "https://heidihealth.com",
]


def build_chrome_options(settings: Settings) -> Options:
    options = Options()
    options.add_argument(f"--user-data-dir={settings.chrome_profile_dir}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--start-maximized")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    # ── Clipboard permission: allow without prompting ──────────────────────
    # This tells Chrome to auto-allow clipboard read/write for all sites,
    # avoiding the "Allow <site> to see text and images copied to clipboard"
    # permission dialog that blocks headless and Docker runs.
    options.add_argument("--enable-unsafe-clipboard")  # legacy helper flag
    options.add_experimental_option("prefs", {
        # 1 = allow, 2 = block, 0 = ask (default)
        "profile.default_content_setting_values.clipboard": 1,
        # Also pre-allow specific origins via the exceptions dictionary
        "profile.content_settings.exceptions.clipboard": {
            f"[*.]heidihealth.com,*": {
                "last_modified": "13244206900000",
                "setting": 1,
            },
            "https://scribe.heidihealth.com:443,*": {
                "last_modified": "13244206900000",
                "setting": 1,
            },
            "https://app.heidihealth.com:443,*": {
                "last_modified": "13244206900000",
                "setting": 1,
            },
        },
    })

    if settings.headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

    return options


def _grant_clipboard_permission_via_cdp(driver: webdriver.Chrome) -> None:
    """Grant clipboard read+write via Chrome DevTools Protocol.

    This is the most reliable way to allow clipboard access in automation —
    it bypasses the user-facing permission prompt entirely.
    """
    for origin in _CLIPBOARD_ALLOWED_ORIGINS:
        try:
            driver.execute_cdp_cmd(
                "Browser.grantPermissions",
                {
                    "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
                    "origin": origin,
                },
            )
        except Exception:
            # CDP command may not be available in all Chrome versions; ignore errors.
            pass


def _purge_chrome_lock_files(profile_dir: Path) -> None:
    """Remove stale Chrome lock files left behind after a crash or SIGKILL.

    When Docker kills the container (exit 137 = OOM/SIGKILL), Chrome doesn't
    get a chance to clean up its profile directory. The persistent Docker volume
    retains SingletonLock / SingletonSocket / SingletonCookieLock files, which
    cause Chrome to exit immediately on the next startup with:
        SessionNotCreatedException: Chrome instance exited

    It is always safe to delete these — they are only meaningful while Chrome
    is actively running. If Chrome is not running, they are stale.
    """
    lock_patterns = [
        "SingletonLock",
        "SingletonSocket",
        "SingletonCookieLock",
        "lockfile",
        ".com.google.Chrome.*",
    ]
    if not profile_dir.exists():
        return
    # Search in both the root and the Default profile subdirectory
    search_dirs = [profile_dir, profile_dir / "Default"]
    import glob
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in lock_patterns:
            for f in glob.glob(str(search_dir / pattern)):
                try:
                    Path(f).unlink(missing_ok=True)
                except OSError:
                    pass


def create_driver(settings: Settings) -> webdriver.Chrome:
    settings.ensure_directories()
    # Purge stale Chrome lock files before launching — prevents
    # "Chrome instance exited" errors after container crashes (exit 137).
    _purge_chrome_lock_files(settings.chrome_profile_dir)
    driver_path = Path(chromedriver_autoinstaller.install())
    service = Service(str(driver_path))
    driver = webdriver.Chrome(service=service, options=build_chrome_options(settings))
    driver.set_page_load_timeout(90)
    driver.implicitly_wait(1)

    # Grant clipboard permission via CDP immediately after driver creation.
    # This works for both headless and visible-browser modes.
    _grant_clipboard_permission_via_cdp(driver)

    return driver

