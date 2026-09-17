"""
Schema-Migrationen fuer die SQLite-Datenbank.

Die Datenbank fuehrt ihre Version in `PRAGMA user_version`. Jede Migration ist
eine nummerierte Funktion; beim Start werden alle Schritte angewendet, deren
Nummer groesser als die aktuelle Version ist. Vor dem ersten Schritt eines
Laufs wird die Datenbankdatei gesichert - das Projekt hat keine Testsuite,
also ist das Backup die Rueckfallebene.

Neue Migration hinzufuegen: Funktion schreiben und unten in MIGRATIONS mit der
naechsten freien Nummer eintragen. Bestehende Schritte werden nie geaendert.
"""
import shutil
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
from typing import Callable, List, Tuple

from utils.logger import setup_logger

logger = setup_logger("migrations")


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """
    Ausgangsschema: die Tabellen, die vor Einfuehrung der Migrationen bereits
    per CREATE TABLE IF NOT EXISTS angelegt wurden. Auf einer bestehenden
    Datenbank ist dieser Schritt ein No-Op, auf einer leeren erzeugt er alles.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            dfb_username_encrypted TEXT,
            dfb_password_encrypted TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS login_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            logged_in_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS download_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            downloaded_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS match_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            heim_team TEXT NOT NULL,
            gast_team TEXT NOT NULL,
            datum TEXT NOT NULL,
            sr_km REAL,
            sr_oevm REAL,
            sra1_km REAL,
            sra1_oevm REAL,
            sra2_km REAL,
            sra2_oevm REAL,
            updated_at TEXT NOT NULL,
            UNIQUE (user_id, heim_team, gast_team, datum),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)


def _migration_002_wal(conn: sqlite3.Connection) -> None:
    """
    WAL-Journal dauerhaft aktivieren. Gleichzeitiges Schreiben aus dem
    Scraper-Kindprozess und Lesen durch die API blockiert sich damit nicht
    mehr gegenseitig. Die Einstellung wird in der Datei gespeichert und gilt
    danach fuer jede Verbindung.
    """
    conn.execute("PRAGMA journal_mode = WAL")


# (Version, Beschreibung, Funktion) - aufsteigend, Luecken sind nicht erlaubt.
MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "baseline schema", _migration_001_baseline),
    (2, "wal journal mode", _migration_002_wal),
]


def _backup_database(db_path: Path, from_version: int) -> Path | None:
    """
    Legt eine Kopie der Datenbank neben der Originaldatei ab, bevor migriert
    wird. Gibt den Pfad des Backups zurueck, oder None wenn es noch keine
    Datenbankdatei gibt (frische Installation - da ist nichts zu sichern).
    """
    if not db_path.exists():
        return None

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.v{from_version}.{stamp}.bak")
    shutil.copy2(db_path, backup_path)
    logger.info(f"Backup vor Migration angelegt: {backup_path}")

    return backup_path


def apply_migrations(conn: sqlite3.Connection, db_path: Path) -> int:
    """
    Bringt die Datenbank auf den neuesten Stand.

    Jeder Schritt laeuft in einer eigenen Transaktion und setzt danach
    user_version. Bricht ein Schritt ab, bleibt die Datenbank auf der letzten
    erfolgreich angewendeten Version stehen und die Exception wird
    weitergereicht - halb migriert startet die App nicht.

    Returns:
        Die Version, auf der die Datenbank nach dem Lauf steht.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    target = MIGRATIONS[-1][0] if MIGRATIONS else 0

    if current >= target:
        logger.debug(f"Schema aktuell (Version {current})")
        return current

    logger.info(f"Migriere Schema von Version {current} auf {target}")
    _backup_database(db_path, current)

    for version, description, migrate in MIGRATIONS:
        if version <= current:
            continue

        logger.info(f"Migration {version}: {description}")
        try:
            migrate(conn)
            # user_version nimmt keine Parameter-Bindung entgegen; die Version
            # stammt aus MIGRATIONS und ist damit keine fremde Eingabe.
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error(f"Migration {version} ({description}) fehlgeschlagen - Abbruch")
            raise

        current = version

    logger.info(f"Schema auf Version {current}")
    return current
