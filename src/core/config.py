"""
Central configuration - where data and secrets live.

Everything mutable lives under DATA_DIR: the .env with the secrets, the
SQLite database and the session folders. In the container DATA_DIR=/data,
so a single folder next to the docker-compose.yml is enough on the server.
Locally it is ./data in the project.

Individual paths can still be overridden via ENV
(ENV_FILE, DATABASE_PATH, OUTPUT_DIR). If nothing exists at the new
location but something does at the old one (project root), the old
location keeps being used - so a half-migrated server does not start with
an empty database.
"""
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from utils.logger import setup_logger

logger = setup_logger("config")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Secrets that can be generated on the very first start. Both must stay
# stable across restarts: ENCRYPTION_KEY decrypts the stored DFB
# credentials, JWT_SECRET_KEY keeps logins valid.
_GENERATED_SECRETS = {
    "JWT_SECRET_KEY": lambda: secrets.token_urlsafe(32),
    "ENCRYPTION_KEY": lambda: Fernet.generate_key().decode(),
}


# Application version. In the published image the release workflow sets it
# from the Git tag (v1.8.2 -> "1.8.2"), see ARG APP_VERSION in the Dockerfile.
#
# The value below is only the fallback for a run from source. It used to be
# the only source and had to be bumped by hand when tagging - which was
# forgotten three times, so v1.8.1 reported itself as 1.7.0: in the health
# endpoint, in the subject of the error reports and in the User-Agent sent
# to fussball.de and Nominatim.
APP_VERSION = os.getenv("APP_VERSION") or "1.10.1"


def get_data_dir() -> Path:
    """Base directory for all mutable data."""
    return Path(os.getenv("DATA_DIR") or PROJECT_ROOT / "data")


def _prefer_existing(preferred: Path, legacy: Path) -> Path:
    """Returns the old path as long as data exists only there."""
    if preferred.exists() or not legacy.exists() or legacy == preferred:
        return preferred

    logger.warning(
        f"Nutze alten Pfad {legacy} - erwartet wurde {preferred}. "
        f"Zum Umziehen die Datei nach {preferred} verschieben."
    )
    return legacy


def get_env_file() -> Path:
    """Path of the .env file holding the secrets."""
    if env_file := os.getenv("ENV_FILE"):
        return Path(env_file)

    return _prefer_existing(get_data_dir() / ".env", PROJECT_ROOT / ".env")


def get_db_path() -> Path:
    """Path of the SQLite database."""
    if db_path := os.getenv("DATABASE_PATH"):
        return Path(db_path)

    return _prefer_existing(get_data_dir() / "app.db", PROJECT_ROOT / "app.db")


def get_output_dir() -> Path:
    """Base directory of the session folders holding the generated documents."""
    if output_dir := os.getenv("OUTPUT_DIR"):
        return Path(output_dir)

    preferred = get_data_dir() / "output"
    legacy = PROJECT_ROOT / "output"

    # Unlike with files, only a *populated* old folder counts here:
    # an empty output/ in the image is no reason to ignore DATA_DIR.
    if not preferred.exists() and legacy.is_dir() and any(legacy.iterdir()):
        return _prefer_existing(preferred, legacy)

    return preferred


def _bootstrap_secrets(env_file: Path) -> None:
    """
    Generates missing secrets on the very first start.

    An existing .env is never touched - otherwise stored DFB credentials
    would become undecryptable.
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
        # Create exclusively: if a second process starts at the same time,
        # exactly one wins and the other reads its keys.
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
    Loads the .env and adds missing secrets on the first start.

    Must run before modules that read secrets at import time (core.security).
    Environment variables that are already set win over the file.
    """
    env_file = get_env_file()
    load_dotenv(env_file)
    _bootstrap_secrets(env_file)
    return env_file
