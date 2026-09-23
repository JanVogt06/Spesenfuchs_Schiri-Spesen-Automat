import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Format: [2025-01-15 14:30:45] INFO - Nachricht
_FORMAT = logging.Formatter(
    '[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Ein Handler je Prozess, den sich alle Logger teilen. None heisst: noch
# nicht versucht; False: versucht, aber nicht moeglich.
_datei_handler = None


def _log_datei() -> Path:
    """
    Wohin das Protokoll geschrieben wird: LOG_FILE, sonst DATA_DIR/logs.

    Bewusst ohne core.config: config importiert diesen Logger beim Laden, ein
    Import in die Gegenrichtung liefe im Kreis.
    """
    if log_file := os.getenv("LOG_FILE"):
        return Path(log_file)

    data_dir = os.getenv("DATA_DIR") or Path(__file__).resolve().parent.parent.parent / "data"
    return Path(data_dir) / "logs" / "spesenfuchs.log"


def _hole_datei_handler() -> Optional[logging.Handler]:
    """
    Der Datei-Handler dieses Prozesses, beim ersten Aufruf angelegt.

    Auf dem Server gibt es sonst nur stdout des Containers - und das ist auf
    einem NAS oft nicht erreichbar. Die Datei liegt im data-Ordner neben der
    Datenbank und laesst sich ueber jeden Dateimanager oeffnen.

    Die naechtlichen Abrufe laufen in eigenen Prozessen, die unter Python
    3.14 per forkserver starten und keine Handler erben. Deshalb entsteht der
    Handler hier, in jedem Prozess neu, statt einmal beim Start. Alle
    Prozesse haengen an dieselbe Datei an; nur das seltene Rotieren koennen
    zwei gleichzeitig laufende Prozesse durcheinanderbringen, und dann geht
    allenfalls ein Stueck Protokoll verloren.
    """
    global _datei_handler

    if _datei_handler is None:
        pfad = _log_datei()
        try:
            pfad.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                pfad, maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8"
            )
            handler.setFormatter(_FORMAT)
            _datei_handler = handler
        except OSError as e:
            print(f"Protokolldatei {pfad} nicht beschreibbar, nur Konsole: {e}", file=sys.stderr)
            _datei_handler = False

    return _datei_handler or None


def setup_logger(name: str = "dfb_scraper", level: int = logging.INFO) -> logging.Logger:
    """
    Richtet einen einfachen Logger ein.

    Args:
        name: Name des Loggers
        level: Log-Level (default: INFO)

    Returns:
        Konfigurierter Logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Verhindere doppelte Handler
    if logger.handlers:
        return logger

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(_FORMAT)
    logger.addHandler(console_handler)

    datei_handler = _hole_datei_handler()
    if datei_handler:
        logger.addHandler(datei_handler)

    return logger
