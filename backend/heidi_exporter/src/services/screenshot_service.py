from __future__ import annotations

from pathlib import Path

from selenium.webdriver.remote.webdriver import WebDriver

from src.database.schemas import SessionMetadata


class ScreenshotService:
    def __init__(self, screenshots_root: Path, enabled: bool = True):
        self.screenshots_root = screenshots_root
        self.enabled = enabled
        self.screenshots_root.mkdir(parents=True, exist_ok=True)

    def directory_for(self, ordinal: int) -> Path:
        directory = self.screenshots_root / f"session_{ordinal:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save(self, driver: WebDriver, directory: Path, name: str) -> Path:
        path = directory / f"{name}.png"
        if self.enabled:
            driver.save_screenshot(str(path))
        return path

