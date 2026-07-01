from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver


class CookieService:
    def __init__(self, cookie_path: Path):
        self.cookie_path = cookie_path
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, driver: WebDriver, base_url: str) -> bool:
        if not self.cookie_path.exists():
            return False
        driver.get(base_url)
        with self.cookie_path.open("r", encoding="utf-8") as handle:
            cookies: list[dict[str, Any]] = json.load(handle)
        loaded = False
        for cookie in cookies:
            safe_cookie = {
                key: value
                for key, value in cookie.items()
                if key in {"name", "value", "domain", "path", "expiry", "secure", "httpOnly", "sameSite"}
            }
            try:
                driver.add_cookie(safe_cookie)
                loaded = True
            except WebDriverException:
                continue
        if loaded:
            driver.refresh()
        return loaded

    def save(self, driver: WebDriver) -> None:
        with self.cookie_path.open("w", encoding="utf-8") as handle:
            json.dump(driver.get_cookies(), handle, indent=2)

