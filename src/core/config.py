"""
Zentrale Konfiguration - wo Daten und Secrets liegen.

Alles Veraenderliche liegt unter DATA_DIR: die .env mit den Secrets, die
SQLite-Datenbank und die Session-Ordner. Im Container ist DATA_DIR=/data,
sodass auf dem Server ein einziger Ordner neben der docker-compose.yml
genuegt. Lokal ist es ./data im Projekt.

Einzelne Pfade lassen sich weiterhin per ENV ueberschreiben
(ENV_FILE, DATABASE_PATH, OUTPUT_DIR). Existiert am neuen Ort nichts, am
alten (Projekt-Root) aber schon, wird der alte Ort weiterbenutzt - damit
ein halb migrierter Server nicht mit leerer Datenbank startet.
"""
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from utils.logger import setup_logger

logger = setup_logger("config")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Secrets, die beim allerersten Start erzeugt werden koennen. Beide muessen
# ueber Neustarts hinweg stabil bleiben: ENCRYPTION_KEY entschluesselt die
# gespeicherten DFB-Zugangsdaten, JWT_SECRET_KEY haelt Logins gueltig.
_GENERATED_SECRETS = {
    "JWT_SECRET_KEY": lambda: secrets.token_urlsafe(32),
    "ENCRYPTION_KEY": lambda: Fernet.generate_key().decode(),
}


# Anwendungsversion. Beim Release mit dem Git-Tag mitziehen (Tag v1.3.0 ->
# "1.3.0"); der Health-Endpunkt meldet genau diesen Wert.
APP_VERSION = "1.6.0"


def get_data_dir() -> Path:
    """Basisverzeichnis fuer alle veraenderlichen Daten."""
    return Path(os.getenv("DATA_DIR") or PROJECT_ROOT / "data")


def _prefer_existing(preferred: Path, legacy: Path) -> Path:
    """Gibt den alten Pfad zurueck, solange nur dort Daten liegen."""
    if preferred.exists() or not legacy.exists() or legacy == preferred:
        return preferred

    logger.warning(
        f"Nutze alten Pfad {legacy} - erwartet wurde {preferred}. "
        f"Zum Umziehen die Datei nach {preferred} verschieben."
    )
    return legacy


def get_env_file() -> Path:
    """Pfad der .env mit den Secrets."""
    if env_file := os.getenv("ENV_FILE"):
        return Path(env_file)

    return _prefer_existing(get_data_dir() / ".env", PROJECT_ROOT / ".env")


def get_db_path() -> Path:
    """Pfad der SQLite-Datenbank."""
    if db_path := os.getenv("DATABASE_PATH"):
        return Path(db_path)

    return _prefer_existing(get_data_dir() / "app.db", PROJECT_ROOT / "app.db")


def get_output_dir() -> Path:
    """Basisverzeichnis der Session-Ordner mit den generierten Dokumenten."""
    if output_dir := os.getenv("OUTPUT_DIR"):
        return Path(output_dir)

    preferred = get_data_dir() / "output"
    legacy = PROJECT_ROOT / "output"

    # Anders als bei Dateien zaehlt hier nur ein *gefuellter* alter Ordner:
    # ein leeres output/ im Image ist kein Grund, DATA_DIR zu ignorieren.
    if not preferred.exists() and legacy.is_dir() and any(legacy.iterdir()):
        return _prefer_existing(preferred, legacy)

    return preferred


def _bootstrap_secrets(env_file: Path) -> None:
    """
    Erzeugt fehlende Secrets beim allerersten Start.

    Eine bereits vorhandene .env wird nie angefasst - sonst wuerden
    gespeicherte DFB-Zugangsdaten unentschluesselbar.
    """
    if env_file.exists():
        return

    missing = {
        name: generate()
        for name, generate in _GENERATED_SECRETS.items()
        if not os.getenv(name)
    }
    if not missing:
        return

    content = "\n".join([
        "# Automatisch beim ersten Start erzeugt.",
        "# NICHT loeschen oder aendern: ENCRYPTION_KEY entschluesselt die",
        "# gespeicherten DFB-Zugangsdaten, JWT_SECRET_KEY haelt Logins gueltig.",
        "",
        *(f"{name}={value}" for name, value in missing.items()),
        "",
    ])

    try:
        env_file.parent.mkdir(parents=True, exist_ok=True)
        # Exklusiv anlegen: startet ein zweiter Prozess gleichzeitig,
        # gewinnt genau einer und der andere liest dessen Schluessel.
        fd = os.open(env_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        load_dotenv(env_file)
        return
    except OSError as e:
        logger.error(f"Konnte {env_file} nicht anlegen: {e}")
        return

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

    os.environ.update(missing)
    logger.warning(
        f"Neue Secrets erzeugt in {env_file} ({', '.join(missing)}). "
        f"Diese Datei sichern - ohne sie sind gespeicherte DFB-Zugangsdaten verloren."
    )


def load_environment() -> Path:
    """
    Laedt die .env und ergaenzt fehlende Secrets beim ersten Start.

    Muss vor Modulen laufen, die Secrets beim Import lesen (core.security).
    Bereits gesetzte Umgebungsvariablen gewinnen gegen die Datei.
    """
    env_file = get_env_file()
    load_dotenv(env_file)
    _bootstrap_secrets(env_file)
    return env_file
