"""
Schema-Migrationen fuer die SQLite-Datenbank.

Die Datenbank fuehrt ihre Version in `PRAGMA user_version`. Jede Migration ist
eine nummerierte Funktion; beim Start werden alle Schritte angewendet, deren
Nummer groesser als die aktuelle Version ist. Vor dem ersten Schritt eines
Laufs wird die Datenbankdatei gesichert - das Projekt hat keine Testsuite,
also ist das Backup die Rueckfallebene.

Neue Migration hinzufuegen: Funktion schreiben und unten in MIGRATIONS mit der
naechsten freien Nummer eintragen. Bestehende Schritte werden nie geaendert.

Beim Deploy gilt: erst die neue Version starten, dann alte Daten wegraeumen.
Der Backfill aus den Session-Ordnern laeuft genau einmal und bricht ab, wenn
die Ordner fehlen, obwohl die Datenbank Sessions kennt.
"""
import json
import os
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
from typing import Callable, List, Tuple

from utils.logger import setup_logger

logger = setup_logger("migrations")


def _run_script(conn: sqlite3.Connection, script: str) -> None:
    """
    Fuehrt mehrere SQL-Anweisungen aus, ohne die laufende Transaktion zu beenden.

    conn.executescript() waere das Naheliegende, gibt aber vor jedem Lauf ein
    COMMIT ab. Damit waere jede DDL sofort dauerhaft und das rollback() im
    Runner wirkungslos: ein Schritt, der in der Mitte scheitert, liesse seine
    halben Tabellen zurueck, waehrend user_version zurueckbleibt - der naechste
    Start scheiterte dann an "table already exists" und die Anwendung kaeme nie
    wieder hoch. SQLite kann DDL transaktional, also fuehren wir die
    Anweisungen einzeln in der offenen Transaktion aus.
    """
    for anweisung in script.split(";"):
        if anweisung.strip():
            conn.execute(anweisung)


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """
    Ausgangsschema: die Tabellen, die vor Einfuehrung der Migrationen bereits
    per CREATE TABLE IF NOT EXISTS angelegt wurden. Auf einer bestehenden
    Datenbank ist dieser Schritt ein No-Op, auf einer leeren erzeugt er alles.
    """
    _run_script(conn, """
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
    _run_script(conn, """
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
    _run_script(conn, """
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


def _migration_005_download_log_matches(conn: sqlite3.Connection) -> None:
    """
    Downloads haengen kuenftig an einem Spiel, nicht mehr an einer Session.

    SQLite kann einer Spalte das NOT NULL nicht nachtraeglich nehmen, also
    wird die Tabelle neu gebaut und der Bestand uebernommen. Die alten Zeilen
    behalten ihre session_id und bekommen kein match_id - sie sind Historie.
    """
    _run_script(conn, """
        CREATE TABLE download_log_neu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            match_id INTEGER,
            session_id TEXT,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            downloaded_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        INSERT INTO download_log_neu
            (id, user_id, session_id, filename, file_type, downloaded_at)
        SELECT id, user_id, session_id, filename, file_type, downloaded_at
        FROM download_log;

        DROP TABLE download_log;
        ALTER TABLE download_log_neu RENAME TO download_log;

        CREATE INDEX idx_download_log_user ON download_log (user_id, downloaded_at DESC);
    """)


def _migration_006_backfill_from_sessions(conn: sqlite3.Connection) -> None:
    """
    Holt die Spiele aus den bestehenden Session-Ordnern in die Datenbank.

    Bis hierher lagen sie ausschliesslich als spesen_data.json unter
    <DATA_DIR>/output/session_*/. Ohne diesen Schritt waere am Tag der
    Umstellung bei jedem User die komplette Spielhistorie aus dem Dashboard
    verschwunden, denn der alte Lesepfad hat die Ordner bei jedem Aufruf neu
    eingelesen.

    Die Ordner werden nach Alter aufsteigend verarbeitet, damit bei mehrfach
    gescrapten Spielen der zuletzt gesehene Stand gewinnt - dieselbe Regel,
    die der alte Endpunkt zur Laufzeit angewandt hat (verlegte Anstosszeiten
    kommen in den Daten tatsaechlich vor).

    Anschliessend werden die bereits erfassten Fahrtkosten aus der alten
    Tabelle match_expenses auf die neuen Zeilen umgehaengt. Die alte Tabelle
    bleibt vorerst stehen - sie ist die Rueckfallebene, falls hier etwas
    schiefgeht.

    Die Helfer werden aus dem Anwendungscode importiert statt hier kopiert:
    der match_key MUSS exakt so gebildet werden wie beim naechtlichen Scrapen,
    sonst legt der erste Lauf nach der Umstellung alles doppelt an.
    """
    # Lokale Importe: db.matches importiert db.database, das wiederum dieses
    # Modul importiert - auf Modulebene waere das ein Zirkelbezug.
    from core import config
    from db.matches import build_match_key, upsert_match
    from generator.spesen_calculator import calculate_spesen
    from utils.match_utils import extract_iso_date_from_anpfiff

    # Kilometersatz, der zum Zeitpunkt dieser Migration galt. Bewusst als
    # Literal: eine spaetere Aenderung der Pauschale darf die eingefrorenen
    # Werte historischer Abrechnungen nicht nachtraeglich verschieben.
    km_satz = 0.30

    # get_output_dir() statt DATA_DIR/"output": eine Installation kann OUTPUT_DIR
    # gesetzt haben oder noch auf dem alten Layout stehen, und dann lagen die
    # Ordner woanders.
    output_dir = config.get_output_dir()

    besitzer = {
        row["session_id"]: row
        for row in conn.execute("SELECT session_id, user_id, created_at FROM sessions")
    }

    ordner = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: (besitzer[d.name]["created_at"] if d.name in besitzer else "", d.name),
    ) if output_dir.exists() else []

    # Kennt die Datenbank Sessions, muessen auch deren Ordner da sein. Sind sie
    # weg, zeigt der Pfad woandershin oder es wurde zu frueh aufgeraeumt. Ohne
    # diese Pruefung liefe der Schritt durch, Migration 007 wuerfe gleich darauf
    # `sessions` weg und die Historie aller Nutzer waere ohne eine einzige
    # Fehlermeldung verloren.
    #
    # Geprueft wird die Zahl der WIEDERGEFUNDENEN Ordner, nicht bloss ob das
    # Verzeichnis existiert: ein "rm -rf data/output/*" laesst das Verzeichnis
    # stehen und waere sonst durchgerutscht.
    bekannt = sum(1 for d in ordner if d.name in besitzer)

    if besitzer and not bekannt and not os.getenv("SKIP_SESSION_BACKFILL"):
        raise RuntimeError(
            f"In {output_dir} liegt kein einziger der {len(besitzer)} Session-Ordner, "
            "die diese Datenbank kennt. Die Spiele koennen nicht uebernommen werden. "
            "Pruefe DATA_DIR/OUTPUT_DIR und lege das Verzeichnis zurueck. Ist der "
            "Verlust gewollt, den Start einmalig mit SKIP_SESSION_BACKFILL=1 wiederholen."
        )

    if besitzer and bekannt < len(besitzer):
        fehlend = len(besitzer) - bekannt
        # Ein paar Sessions ohne Ordner sind normal: Laeufe, die schon beim
        # DFB-Login scheiterten, haben nie etwas geschrieben. Erst wenn ein
        # nennenswerter Teil fehlt, ist das ein Hinweis auf ein Problem.
        melden = logger.warning if fehlend > len(besitzer) // 10 else logger.info
        melden(
            f"{fehlend} von {len(besitzer)} Sessions haben keinen Ordner "
            "(in der Regel Laeufe, die vor dem Scrapen abgebrochen sind)."
        )

    spiele = uebersprungen = ohne_besitzer = 0

    for verzeichnis in ordner:
        session = besitzer.get(verzeichnis.name)
        if not session:
            # Ordner ohne Datenbankzeile - niemand kann ihn besitzen
            ohne_besitzer += 1
            continue

        datei = verzeichnis / "spesen_data.json"
        if not datei.exists():
            continue

        try:
            matches = json.loads(datei.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"{verzeichnis.name}: spesen_data.json unlesbar ({e})")
            uebersprungen += 1
            continue

        for match_data in matches:
            try:
                spiel_info = match_data.get("spiel_info", {}) or {}
                datum = extract_iso_date_from_anpfiff(spiel_info.get("anpfiff", ""))
                sr_spesen, sra_spesen = calculate_spesen(
                    spiel_info.get("spielklasse", ""),
                    spiel_info.get("mannschaftsart", ""),
                )
                upsert_match(
                    session["user_id"], match_data, datum,
                    sr_spesen, sra_spesen, km_satz,
                    scraped_at=session["created_at"],
                    conn=conn,
                )
                spiele += 1
            except Exception as e:
                logger.warning(f"{verzeichnis.name}: Spiel uebersprungen ({e})")
                uebersprungen += 1

    gesamt = conn.execute("SELECT COUNT(*) AS n FROM matches").fetchone()["n"]
    logger.info(
        f"Uebernommen: {spiele} Datensaetze aus {len(ordner)} Ordnern -> {gesamt} Spiele "
        f"({uebersprungen} uebersprungen, {ohne_besitzer} Ordner ohne Session-Zeile)"
    )

    # Erfasste Fahrtkosten auf die neuen Zeilen umhaengen. Der alte Schluessel
    # war (user_id, heim_team, gast_team, datum) - genau die Felder, aus denen
    # bei Spielen mit Teams auch der match_key besteht.
    uebernommen = 0
    for alt in conn.execute("SELECT * FROM match_expenses").fetchall():
        treffer = conn.execute("""
            SELECT id FROM matches
            WHERE user_id = ? AND heim_team = ? AND gast_team = ? AND datum = ?
        """, (alt["user_id"], alt["heim_team"], alt["gast_team"], alt["datum"])).fetchone()

        if not treffer:
            logger.warning(
                f"Fahrtkosten ohne passendes Spiel: user {alt['user_id']}, "
                f"{alt['heim_team']} vs {alt['gast_team']} am {alt['datum']}"
            )
            continue

        for rolle, seq, praefix in (("SR", 0, "sr"), ("SRA 1", 0, "sra1"), ("SRA 2", 0, "sra2")):
            km, oevm = alt[f"{praefix}_km"], alt[f"{praefix}_oevm"]
            if km is None and oevm is None:
                continue

            conn.execute("""
                INSERT INTO official_expenses (match_id, rolle, seq, km, oevm, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (match_id, rolle, seq) DO UPDATE SET
                    km = excluded.km, oevm = excluded.oevm, updated_at = excluded.updated_at
            """, (treffer["id"], rolle, seq, km, oevm, alt["updated_at"]))
            uebernommen += 1

    logger.info(f"{uebernommen} erfasste Fahrtkosten-Eintraege uebernommen")


def _migration_007_drop_legacy_tables(conn: sqlite3.Connection) -> None:
    """
    Raeumt die Tabellen weg, die seit dem Umstieg auf die datenbankgestuetzten
    Spiele niemand mehr anspricht.

    `sessions` beschrieb einen Ordner unter data/output, den es nicht mehr gibt.
    `match_expenses` war die flache Vorgaengerin von `official_expenses` mit
    genau drei festen Rollen pro Spiel.

    Beide wurden in Migration 006 ein letztes Mal gelesen. Danach sind sie tot -
    im Code steht kein einziger Zugriff mehr. Faellt der Backfill doch noch
    einmal auf die Fuesse, ist die Rueckfallebene die Sicherungskopie, die der
    Runner vor jedem Lauf neben app.db legt.

    `download_log.session_id` bleibt bestehen: die Spalte traegt die Historie
    der Downloads aus der Zeit vor der Umstellung.
    """
    _run_script(conn, """
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS match_expenses;
    """)


def _migration_008_rekey_matches(conn: sqlite3.Connection) -> None:
    """
    Berechnet match_key fuer bestehende Zeilen nach der erweiterten Regel neu.

    Der Schluessel enthaelt jetzt auch Mannschaftsart und Spielklasse. Ohne
    diesen Schritt bildete der naechste Scrape neue Schluessel, fuende die
    bestehenden Zeilen nicht wieder und legte jedes Spiel ein zweites Mal an -
    samt Verlust der Verbindung zu den eingetragenen Kilometern.

    Zusaetzliche Bestandteile koennen nur trennen, nie zusammenfuehren, also
    kann dabei kein Konflikt mit UNIQUE(user_id, match_key) entstehen.

    Was dieser Schritt NICHT kann: eine Ansetzung zurueckholen, die vorher von
    einer anderen ueberschrieben wurde. Die taucht beim naechsten Scrape als
    eigene Zeile auf.
    """
    from db.matches import build_match_key

    zeilen = conn.execute("""
        SELECT id, match_key, heim_team, gast_team, datum, anpfiff,
               mannschaftsart, spielklasse, staette_name
        FROM matches
    """).fetchall()

    geaendert = 0
    for zeile in zeilen:
        neuer_key = build_match_key(
            {
                "heim_team": zeile["heim_team"],
                "gast_team": zeile["gast_team"],
                "anpfiff": zeile["anpfiff"],
                "mannschaftsart": zeile["mannschaftsart"],
                "spielklasse": zeile["spielklasse"],
            },
            {"name": zeile["staette_name"]},
            zeile["datum"],
        )

        if neuer_key != zeile["match_key"]:
            conn.execute("UPDATE matches SET match_key = ? WHERE id = ?", (neuer_key, zeile["id"]))
            geaendert += 1

    logger.info(f"{geaendert} von {len(zeilen)} Spielen haben einen neuen match_key")


# (Version, Beschreibung, Funktion) - aufsteigend, Luecken sind nicht erlaubt.
MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "baseline schema", _migration_001_baseline),
    (2, "wal journal mode", _migration_002_wal),
    (3, "matches, officials and expenses", _migration_003_matches),
    (4, "scrape runs replace session metadata", _migration_004_scrape_runs),
    (5, "downloads reference matches", _migration_005_download_log_matches),
    (6, "backfill matches from session folders", _migration_006_backfill_from_sessions),
    (7, "drop legacy session and expense tables", _migration_007_drop_legacy_tables),
    (8, "rekey matches by mannschaftsart and spielklasse", _migration_008_rekey_matches),
]


def _backup_database(conn: sqlite3.Connection, db_path: Path, from_version: int) -> Path | None:
    """
    Legt eine Kopie der Datenbank neben der Originaldatei ab, bevor migriert
    wird. Gibt den Pfad des Backups zurueck, oder None wenn es noch keine
    Datenbankdatei gibt (frische Installation - da ist nichts zu sichern).

    Bewusst ueber die Backup-API von SQLite und nicht per Dateikopie: sobald
    die Datenbank im WAL-Modus laeuft (ab Migration 002), stehen frisch
    committete Daten noch in app.db-wal. Ein shutil.copy2 nimmt nur app.db mit
    und liefert damit eine stille Teilsicherung - genau dann wertlos, wenn sie
    gebraucht wird. backup() zieht einen konsistenten Schnappschuss inklusive
    WAL-Inhalt.
    """
    if not db_path.exists():
        return None

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.v{from_version}.{stamp}.bak")

    ziel = sqlite3.connect(backup_path)
    try:
        conn.backup(ziel)
    finally:
        ziel.close()

    logger.info(f"Backup vor Migration angelegt: {backup_path}")

    return backup_path


def apply_migrations(conn: sqlite3.Connection, db_path: Path) -> int:
    """
    Bringt die Datenbank auf den neuesten Stand.

    Jeder Schritt laeuft in einer eigenen Transaktion und setzt danach
    user_version. Bricht ein Schritt ab, wird er vollstaendig zurueckgerollt,
    die Datenbank bleibt auf der letzten erfolgreich angewendeten Version und
    die Exception wird weitergereicht - halb migriert startet die App nicht.
    Ein erneuter Start nimmt den gescheiterten Schritt sauber noch einmal.

    Returns:
        Die Version, auf der die Datenbank nach dem Lauf steht.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    target = MIGRATIONS[-1][0] if MIGRATIONS else 0

    if current >= target:
        logger.debug(f"Schema aktuell (Version {current})")
        return current

    logger.info(f"Migriere Schema von Version {current} auf {target}")
    _backup_database(conn, db_path, current)

    for version, description, migrate in MIGRATIONS:
        if version <= current:
            continue

        logger.info(f"Migration {version}: {description}")
        try:
            # Ausdrueckliches BEGIN: Pythons sqlite3 oeffnet von sich aus keine
            # Transaktion fuer DDL, und ohne eine ist rollback() folgenlos.
            # journal_mode vertraegt keine offene Transaktion, deshalb die
            # Ausnahme fuer Schritt 2.
            transaktional = migrate is not _migration_002_wal
            if transaktional:
                conn.execute("BEGIN")

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
