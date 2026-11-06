"""Настройка логирования: консоль + файл в data/logs/factory.log."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import Settings
from .utils import ensure_dir

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(settings: Optional[Settings] = None, level: Optional[str] = None) -> logging.Logger:
    """Идемпотентно настраивает корневой логгер. Возвращает логгер проекта."""
    logger = logging.getLogger("content_factory")
    if getattr(logger, "_configured", False):
        return logger

    log_level = (level or (settings.app.get("log_level") if settings else None) or "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if settings is not None:
        try:
            logs_dir = ensure_dir(settings.logs_dir)
            file_handler = RotatingFileHandler(
                logs_dir / "factory.log",
                maxBytes=2_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            logger.warning("Не удалось открыть файл лога, пишу только в консоль")

    logger._configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"content_factory.{name}")
