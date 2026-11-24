import logging
import multiprocessing
import os
import sys
from logging.handlers import RotatingFileHandler, WatchedFileHandler
from pathlib import Path
from typing import Optional

# Format: [2025-01-15 14:30:45] INFO - message
_FORMAT = logging.Formatter(
    '[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# One handler per process, shared by all loggers. None means: not
# tried yet; False: tried, but not possible.
_datei_handler = None


def _log_datei() -> Path:
    """
    Where the log is written: LOG_FILE, otherwise DATA_DIR/logs.

    Deliberately without core.config: config imports this logger while loading, an
    import in the opposite direction would be circular.
    """
    if log_file := os.getenv("LOG_FILE"):
        return Path(log_file)

    data_dir = os.getenv("DATA_DIR") or Path(__file__).resolve().parent.parent.parent / "data"
    return Path(data_dir) / "logs" / "spesenfuchs.log"


def _hole_datei_handler() -> Optional[logging.Handler]:
    """
    This process's file handler, created on the first call.

    On the server there is otherwise only the container's stdout - and on
    a NAS that is often not reachable. The file sits in the data folder next to the
    database and can be opened with any file manager.

    The fetches run in their own processes, which under Python 3.14 start via
    forkserver and inherit no handlers. That is why the handler is created
    here, anew in every process, instead of once at startup.

    Only the main process may rotate. If two processes rotated the same
    file, each would rename it on its own, and part of the log
    would end up in a file that is overwritten right afterwards. The
    fetch processes therefore only append and reopen the file as soon as the
    main process has rolled it away.
    """
    global _datei_handler

    if _datei_handler is None:
        pfad = _log_datei()
        try:
            pfad.parent.mkdir(parents=True, exist_ok=True)
            if multiprocessing.parent_process() is None:
                handler = RotatingFileHandler(
                    pfad, maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8"
                )
            else:
                handler = WatchedFileHandler(pfad, encoding="utf-8")
            handler.setFormatter(_FORMAT)
            _datei_handler = handler
        except OSError as e:
            print(f"Protokolldatei {pfad} nicht beschreibbar, nur Konsole: {e}", file=sys.stderr)
            _datei_handler = False

    return _datei_handler or None


def setup_logger(name: str = "dfb_scraper", level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a simple logger.

    Args:
            name: Name of the logger
            level: Log level (default: INFO)

    Returns:
            Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(_FORMAT)
    logger.addHandler(console_handler)

    datei_handler = _hole_datei_handler()
    if datei_handler:
        logger.addHandler(datei_handler)

    return logger
