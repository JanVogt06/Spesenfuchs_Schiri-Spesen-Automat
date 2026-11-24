"""
Database module - SQLite database for users and sessions
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Optional

from core import config
from db.migrations import apply_migrations
from utils.logger import setup_logger

logger = setup_logger("database")

# Wait time before SQLite gives up on a locked database. The scraper
# runs in its own process and writes while the API reads.
BUSY_TIMEOUT_MS = 5000


# Database path
def get_db_path() -> Path:
    """Returns the database path (DATABASE_PATH or DATA_DIR/app.db)"""
    path = config.get_db_path()

    # Create the directory if it does not exist
    path.parent.mkdir(exist_ok=True, parents=True)

    return path


DB_PATH = get_db_path()


def get_connection() -> sqlite3.Connection:
    """Creates a DB connection with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Both pragmas apply only to this connection and must therefore be set anew on
    # each one - unlike journal_mode, which is stored in the file.
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_database():
    """Brings the schema up to date via migrations"""
    conn = get_connection()
    try:
        version = apply_migrations(conn, DB_PATH)
    finally:
        conn.close()

    logger.info(f"Datenbank initialisiert: {DB_PATH} (Schema-Version {version})")


# ===== USER FUNCTIONS =====

def create_user(email: str, password_hash: str) -> int:
    """
    Creates a new user.

    Args:
            email: User email
            password_hash: Hashed password

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
    Finds a user by email.

    Returns:
            User dict or None
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Case hardly ever matters for email addresses. Older
    # databases may still contain the same address in two spellings;
    # then the exactly matching one wins, otherwise the oldest.
    cursor.execute("""
        SELECT * FROM users WHERE email = ? COLLATE NOCASE
        ORDER BY (email = ?) DESC, id
        LIMIT 1
    """, (email.strip(), email.strip()))
    user = cursor.fetchone()

    conn.close()

    if user:
        return dict(user)
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Finds a user by ID"""
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
    Returns all users.

    Returns:
            List of user dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users")
    users = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return users


def update_dfb_credentials(user_id: int, encrypted_username: str, encrypted_password: str):
    """
    Stores encrypted DFB credentials for a user.

    Args:
            user_id: User ID
            encrypted_username: Encrypted username
            encrypted_password: Encrypted password
    """
    conn = get_connection()
    cursor = conn.cursor()

    # New credentials are unverified - an old rejection notice
    # no longer applies to them.
    cursor.execute("""
        UPDATE users 
        SET dfb_username_encrypted = ?, dfb_password_encrypted = ?,
            dfb_login_abgelehnt_seit = NULL
        WHERE id = ?
    """, (encrypted_username, encrypted_password, user_id))

    conn.commit()
    conn.close()


def get_dfb_credentials(user_id: int) -> Optional[Dict]:
    """
    Fetches encrypted DFB credentials for a user.

    Returns:
            Dict with dfb_username_encrypted and dfb_password_encrypted, or None
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


def dfb_login_abgelehnt(user_id: int) -> None:
    """
    DFBnet has rejected the stored credentials.

    The first point in time is kept: every further night with the same
    error changes nothing about since when no data has been arriving.
    """
    conn = get_connection()

    try:
        conn.execute("""
            UPDATE users SET dfb_login_abgelehnt_seit = COALESCE(dfb_login_abgelehnt_seit, ?)
            WHERE id = ?
        """, (datetime.now(UTC).isoformat(), user_id))
        conn.commit()
    finally:
        conn.close()


def dfb_login_angenommen(user_id: int) -> None:
    """DFBnet has accepted the credentials - an old notice resolves itself."""
    conn = get_connection()

    try:
        conn.execute(
            "UPDATE users SET dfb_login_abgelehnt_seit = NULL WHERE id = ?", (user_id,)
        )
        conn.commit()
    finally:
        conn.close()


def update_user_password(user_id: int, password_hash: str) -> bool:
    """
    Updates a user's password.

    Args:
            user_id: ID of the user
            password_hash: New password hash

    Returns:
            True if successful
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

# ===== LOGIN LOG FUNCTIONS =====

def log_login(user_id: int) -> None:
    """Records a successful login (for usage statistics)"""
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
    Records a download (for usage statistics).

    Downloads are attached to a match; session_id only exists for the
    legacy endpoints, as long as those exist.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO download_log (user_id, match_id, session_id, filename, file_type, downloaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, match_id, session_id, filename, file_type, datetime.now(UTC).isoformat()))

    conn.commit()
    conn.close()


def log_spielbericht(user_id: int, spielbericht_id: int, aktion: str,
                     quelle: str = "direkt", dokument_id: Optional[int] = None) -> None:
    """
    Records the opening of a match report or its documents (usage statistics).

    The same entry within 10 seconds counts only once - a
    double click or a quick reload is not a second access.
    """
    jetzt = datetime.now(UTC)
    conn = get_connection()

    try:
        doppelt = conn.execute("""
            SELECT 1 FROM spielbericht_log
            WHERE user_id = ? AND spielbericht_id = ? AND aktion = ? AND quelle = ?
              AND COALESCE(dokument_id, 0) = COALESCE(?, 0) AND geklickt_am >= ?
            LIMIT 1
        """, (user_id, spielbericht_id, aktion, quelle, dokument_id,
              (jetzt - timedelta(seconds=10)).isoformat())).fetchone()
        if doppelt:
            return

        conn.execute("""
            INSERT INTO spielbericht_log (user_id, spielbericht_id, dokument_id, aktion, quelle, geklickt_am)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, spielbericht_id, dokument_id, aktion, quelle, jetzt.isoformat()))
        conn.commit()
    finally:
        conn.close()


def count_downloads() -> int:
    """Total number of all downloads - for the number on the start page."""
    conn = get_connection()

    try:
        return conn.execute("SELECT COUNT(*) AS n FROM download_log").fetchone()["n"] or 0
    finally:
        conn.close()
