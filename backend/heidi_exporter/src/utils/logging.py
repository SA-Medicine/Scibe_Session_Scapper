from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from rich.logging import RichHandler


class _JsonFileHandler(logging.FileHandler):
    """Writes one JSON object per line alongside the plain log file for SSE streaming."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": int(time.time() * 1000),
                "level": record.levelname,
                "msg": self.format(record),
                "src": f"{record.filename}:{record.lineno}",
                "logger": record.name,
            }
            self.stream.write(json.dumps(entry) + "\n")
            self.flush()
        except Exception:
            self.handleError(record)


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)

    plain_handler = logging.FileHandler(log_dir / "heidi_exporter.log", encoding="utf-8")
    plain_handler.setFormatter(logging.Formatter("%(message)s"))

    json_handler = _JsonFileHandler(log_dir / "heidi_exporter.jsonl", encoding="utf-8")
    json_handler.setFormatter(logging.Formatter("%(message)s"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(rich_tracebacks=True, markup=True),
            plain_handler,
            json_handler,
        ],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
