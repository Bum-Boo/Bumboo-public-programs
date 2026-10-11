"""Small structured local logs; no frame spam and no source document bodies."""

import json
import logging
from logging.handlers import RotatingFileHandler

from .config import location
from .models import now_iso


def setup_logging():
    directory = location("state")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    logger = logging.getLogger("grimoire")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            directory / "events.jsonl", maxBytes=524288, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def record(event, **fields):
    logging.getLogger("grimoire").info(
        json.dumps({"at": now_iso(), "event": event, **fields}, ensure_ascii=False)
    )
