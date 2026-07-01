from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    heidi_email: str | None
    heidi_password: str | None
    database_url: str
    headless: bool
    max_retries: int
    screenshots_enabled: bool
    heidi_base_url: str
    project_root: Path = PROJECT_ROOT
    screenshots_dir: Path = PROJECT_ROOT / "screenshots"
    checkpoints_dir: Path = PROJECT_ROOT / "checkpoints"
    exports_dir: Path = PROJECT_ROOT / "exports"
    logs_dir: Path = PROJECT_ROOT / "logs"
    chrome_profile_dir: Path = PROJECT_ROOT / "chrome_profile"
    cookies_dir: Path = PROJECT_ROOT / "cookies"
    heidi_cookie_path: Path = PROJECT_ROOT / "cookies" / "heidi_cookies.json"

    @classmethod
    def load(cls, env_path: Path | None = None) -> "Settings":
        load_dotenv(env_path or PROJECT_ROOT / ".env")
        default_db = f"sqlite:///{PROJECT_ROOT / 'heidi_archive.db'}"
        return cls(
            heidi_email=os.getenv("HEIDI_EMAIL") or None,
            heidi_password=os.getenv("HEIDI_PASSWORD") or None,
            database_url=os.getenv("DATABASE_URL", default_db),
            headless=_to_bool(os.getenv("HEADLESS"), False),
            max_retries=int(os.getenv("MAX_RETRIES", "5")),
            screenshots_enabled=_to_bool(os.getenv("SCREENSHOTS_ENABLED"), True),
            heidi_base_url=os.getenv("HEIDI_BASE_URL", "https://scribe.heidihealth.com"),
        )

    def ensure_directories(self) -> None:
        for directory in (
            self.screenshots_dir,
            self.checkpoints_dir,
            self.exports_dir,
            self.logs_dir,
            self.chrome_profile_dir,
            self.cookies_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
