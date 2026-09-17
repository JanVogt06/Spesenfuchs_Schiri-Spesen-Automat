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


def _migration_003_matches(conn: sqlite3.Connection) -> None:
    """
    Die gescrapten Spiele selbst. Bisher lagen sie nur als spesen_data.json in
    den Session-Ordnern; ab hier sind sie die Quelle der Wahrheit.

    Zwei Entwurfsentscheidungen, die nicht offensichtlich sind:

    1. `match_key` statt eines natuerlichen Schluessels aus den Spalten.
       DFBnet liefert (noch) keine Spielnummer, die Identitaet ist also
       Heim + Gast + Datum. Sobald die Spielnummer verfuegbar ist, wird sie
       einfach der neue match_key - Fremdschluessel auf `matches.id` bleiben
       unberuehrt. Turnier-Ansetzungen ohne Teams bekommen einen Schluessel
       aus Spielstaette und Anpfiff, sonst wuerden mehrere Turniere am selben
       Tag kollidieren.

    2. `match_officials` ist ein Schnappschuss pro Spiel, keine Personen-
       Tabelle. Zwei Schiedsrichter koennen denselben Namen tragen, und eine
       Adressaenderung mitten in der Saison darf die Anschrift in einer
       bereits abgegebenen Abrechnung nicht rueckwirkend aendern.

    Aus demselben Grund werden auch die Spesensaetze und der km-Satz beim
    Scrapen eingefroren statt bei jedem Rendern neu berechnet.
    """
    conn.executescript("""
        CREATE TABLE matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,

            -- Identitaet
            match_key TEXT NOT NULL,
            spielnummer TEXT,

            -- Spiel-Info (Schnappschuss des Scrapes)
            heim_team TEXT NOT NULL DEFAULT '',
            gast_team TEXT NOT NULL DEFAULT '',
            datum TEXT NOT NULL,
            anpfiff TEXT,
            mannschaftsart TEXT,
            spielklasse TEXT,
            staffel TEXT,
            spieltag TEXT,

            -- Spielstaette (Schnappschuss)
            staette_name TEXT,
            staette_adresse TEXT,
            staette_platz_typ TEXT,

            -- Eingefrorene Saetze, damit Dokumente reproduzierbar bleiben
            sr_spesen REAL,
            sra_spesen REAL,
            km_satz REAL NOT NULL,

            -- Lebenszyklus
            first_seen_at TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            missing_since TEXT,

            UNIQUE (user_id, match_key),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE INDEX idx_matches_user_datum ON matches (user_id, datum);

        CREATE TABLE match_officials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            rolle TEXT NOT NULL,
            seq INTEGER NOT NULL,
            name TEXT,
            telefon TEXT,
            email TEXT,
            strasse TEXT,
            plz_ort TEXT,
            UNIQUE (match_id, rolle, seq),
            FOREIGN KEY (match_id) REFERENCES matches (id) ON DELETE CASCADE
        );

        CREATE TABLE official_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            rolle TEXT NOT NULL,
            seq INTEGER NOT NULL,
            km REAL,
            oevm REAL,
            updated_at TEXT NOT NULL,
            UNIQUE (match_id, rolle, seq),
            FOREIGN KEY (match_id) REFERENCES matches (id) ON DELETE CASCADE
        );
    """)


def _migration_004_scrape_runs(conn: sqlite3.Connection) -> None:
    """
    Ersetzt die metadata.json im Session-Ordner. Der Scraper laeuft in einem
    eigenen Prozess (Playwright vertraegt sich nicht mit dem asyncio-Loop),
    schrieb seinen Fortschritt bisher in diese Datei und die API las sie fuer
    den 2-Sekunden-Poll wieder aus. Diese Zeile ist jetzt der Kanal.

    error_code traegt weiterhin die Werte, auf die das Frontend prueft
    (DFB_CREDENTIALS_INVALID leitet den User in die Einstellungen).
    """
    conn.executescript("""
        CREATE TABLE scrape_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            step TEXT,
            current_item INTEGER NOT NULL DEFAULT 0,
            total_items INTEGER NOT NULL DEFAULT 0,
            matches_found INTEGER,
            error_code TEXT,
            error_message TEXT,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE INDEX idx_scrape_runs_user_started ON scrape_runs (user_id, started_at DESC);
    """)


# (Version, Beschreibung, Funktion) - aufsteigend, Luecken sind nicht erlaubt.
MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "baseline schema", _migration_001_baseline),
    (2, "wal journal mode", _migration_002_wal),
    (3, "matches, officials and expenses", _migration_003_matches),
    (4, "scrape runs replace session metadata", _migration_004_scrape_runs),
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
