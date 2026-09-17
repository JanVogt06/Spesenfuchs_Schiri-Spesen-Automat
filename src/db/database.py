"""
Database Modul - SQLite Datenbank fuer User und Sessions
"""
import sqlite3
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Optional

from core import config
from db.migrations import apply_migrations
from utils.logger import setup_logger

logger = setup_logger("database")

# Wartezeit, bevor SQLite bei einer gesperrten Datenbank aufgibt. Der Scraper
# laeuft in einem eigenen Prozess und schreibt waehrend die API liest.
BUSY_TIMEOUT_MS = 5000


# Datenbankpfad
def get_db_path() -> Path:
    """Gibt Datenbank-Pfad zurueck (DATABASE_PATH oder DATA_DIR/app.db)"""
    path = config.get_db_path()

    # Erstelle Verzeichnis falls nicht existiert
    path.parent.mkdir(exist_ok=True, parents=True)

    return path


DB_PATH = get_db_path()


def get_connection() -> sqlite3.Connection:
    """Erstellt DB-Verbindung mit Row Factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Beide Pragmas gelten nur fuer diese Verbindung und muessen daher bei
    # jeder neu gesetzt werden - anders als journal_mode, das in der Datei steht.
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_database():
    """Bringt das Schema per Migrationen auf den aktuellen Stand"""
    conn = get_connection()
    try:
        version = apply_migrations(conn, DB_PATH)
    finally:
        conn.close()

    logger.info(f"Datenbank initialisiert: {DB_PATH} (Schema-Version {version})")


# ===== USER FUNKTIONEN =====

def create_user(email: str, password_hash: str) -> int:
    """
    Erstellt neuen User.

    Args:
        email: User Email
        password_hash: Gehashtes Passwort

    Returns:
        User ID
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (email, password_hash, created_at)
        VALUES (?, ?, ?)
    """, (email, password_hash, datetime.now(UTC).isoformat()))

    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return user_id


def get_user_by_email(email: str) -> Optional[Dict]:
    """
    Findet User anhand Email.

    Returns:
        User Dict oder None
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    conn.close()

    if user:
        return dict(user)
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Findet User anhand ID"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    conn.close()

    if user:
        return dict(user)
    return None


def get_all_users() -> List[Dict]:
    """
    Gibt alle User zurueck.

    Returns:
        Liste von User Dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users")
    users = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return users


def update_dfb_credentials(user_id: int, encrypted_username: str, encrypted_password: str):
    """
    Speichert verschluesselte DFB-Credentials fuer User.

    Args:
        user_id: User ID
        encrypted_username: Verschluesselter Username
        encrypted_password: Verschluesseltes Passwort
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users 
        SET dfb_username_encrypted = ?, dfb_password_encrypted = ?
        WHERE id = ?
    """, (encrypted_username, encrypted_password, user_id))

    conn.commit()
    conn.close()


def get_dfb_credentials(user_id: int) -> Optional[Dict]:
    """
    Holt verschluesselte DFB-Credentials fuer User.

    Returns:
        Dict mit dfb_username_encrypted und dfb_password_encrypted oder None
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT dfb_username_encrypted, dfb_password_encrypted 
        FROM users 
        WHERE id = ?
    """, (user_id,))

    result = cursor.fetchone()
    conn.close()

    if result and result['dfb_username_encrypted'] and result['dfb_password_encrypted']:
        return dict(result)
    return None


def update_user_password(user_id: int, password_hash: str) -> bool:
    """
    Aktualisiert das Passwort eines Users.

    Args:
        user_id: ID des Users
        password_hash: Neuer Passwort-Hash

    Returns:
        True wenn erfolgreich
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()

# ===== LOGIN LOG FUNKTIONEN =====

def log_login(user_id: int) -> None:
    """Protokolliert einen erfolgreichen Login (fuer Nutzungsstatistik)"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO login_log (user_id, logged_in_at) VALUES (?, ?)",
        (user_id, datetime.now(UTC).isoformat())
    )

    conn.commit()
    conn.close()


def log_download(user_id: int, filename: str, file_type: str,
                 match_id: Optional[int] = None, session_id: Optional[str] = None) -> None:
    """
    Protokolliert einen Download (fuer Nutzungsstatistik).

    Downloads haengen an einem Spiel; session_id gibt es nur noch fuer die
    Altlast-Endpunkte, solange die existieren.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO download_log (user_id, match_id, session_id, filename, file_type, downloaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, match_id, session_id, filename, file_type, datetime.now(UTC).isoformat()))

    conn.commit()
    conn.close()


def count_downloads() -> int:
    """Gesamtzahl aller Downloads - fuer die Zahl auf der Startseite."""
    conn = get_connection()

    try:
        return conn.execute("SELECT COUNT(*) AS n FROM download_log").fetchone()["n"] or 0
    finally:
        conn.close()
