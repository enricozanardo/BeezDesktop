"""
BeezDesktop Logging Configuration

Sets up file-based logging with rotation so users can inspect issues.
Log files are stored in ~/.beezdesktop/logs/ with automatic rotation
(5 MB per file, 5 backups kept).

All print() output from the app is also captured to the log file via
a stdout/stderr tee, ensuring nothing is lost even from third-party libs.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_DIR = Path.home() / ".beezdesktop" / "logs"
LOG_FILE = LOG_DIR / "beezdesktop.log"
MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file
BACKUP_COUNT = 5               # keep 5 rotated files

_initialized = False


class _TeeStream:
    """Writes to both the original stream and a logger."""

    def __init__(self, original, logger: logging.Logger, level: int):
        self._original = original
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, text: str):
        self._original.write(text)
        if text and text.strip():
            self._logger.log(self._level, text.rstrip())

    def flush(self):
        self._original.flush()

    def fileno(self):
        return self._original.fileno()

    def isatty(self):
        return False


def get_log_path() -> Path:
    """Return the path to the current log file."""
    return LOG_FILE


def setup_logging(level: str = "DEBUG") -> logging.Logger:
    """Initialise rotating file logger and tee stdout/stderr.

    Args:
        level: Logging level name (DEBUG, INFO, WARNING, ERROR).

    Returns:
        The root 'beezdesktop' logger.
    """
    global _initialized
    if _initialized:
        return logging.getLogger("beezdesktop")

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.DEBUG)

    logger = logging.getLogger("beezdesktop")
    logger.setLevel(log_level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8",
    )
    fh.setLevel(log_level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(stream=sys.__stdout__)
    ch.setLevel(log_level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Tee stdout/stderr so print() calls also land in the log file
    tee_logger = logging.getLogger("beezdesktop.stdout")
    tee_logger.setLevel(logging.DEBUG)
    tee_logger.propagate = False
    tee_fh = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8",
    )
    tee_fh.setLevel(logging.DEBUG)
    tee_fh.setFormatter(logging.Formatter(
        "%(asctime)s  PRINT     %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    ))
    tee_logger.addHandler(tee_fh)

    sys.stdout = _TeeStream(sys.__stdout__, tee_logger, logging.INFO)
    sys.stderr = _TeeStream(sys.__stderr__, tee_logger, logging.ERROR)

    _initialized = True

    logger.info("Logging initialised  →  %s", LOG_FILE)
    return logger
