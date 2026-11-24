"""
Schema migrations for the SQLite database.

The database keeps its version in `PRAGMA user_version`. Each migration is a
numbered function; on startup all steps whose number is greater than the
current version are applied. Before the first step of a run the database file
is backed up - the project has no test suite, so the backup is the fallback.

Adding a new migration: write a function and register it in MIGRATIONS below
under the next free number. Existing steps are never changed.

When deploying: first start the new version, then clear away old data.
The backfill from the session folders runs exactly once and aborts if the
folders are missing even though the database knows sessions.
"""
import json
import os
import re
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
from typing import Callable, List, Tuple

from utils.logger import setup_logger

logger = setup_logger("migrations")


def _run_script(conn: sqlite3.Connection, script: str) -> None:
    """
    Executes several SQL statements without ending the running transaction.

    conn.executescript() would be the obvious choice, but it issues a COMMIT
    before every run. That would make every DDL permanent immediately and the
    rollback() in the runner ineffective: a step failing halfway would leave
    its half-built tables behind while user_version stays behind - the next
    start would then fail on "table already exists" and the application would
    never come up again. SQLite supports transactional DDL, so we execute the
    statements one by one inside the open transaction.
    """
    for anweisung in script.split(";"):
        if anweisung.strip():
            conn.execute(anweisung)


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """
    Baseline schema: the tables that were already created via
    CREATE TABLE IF NOT EXISTS before migrations were introduced. On an
    existing database this step is a no-op, on an empty one it creates
    everything.
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
    Enable the WAL journal permanently. Concurrent writing from the scraper
    child process and reading by the API then no longer block each other.
    The setting is stored in the file and applies to every connection
    afterwards.
    """
    conn.execute("PRAGMA journal_mode = WAL")


def _migration_003_matches(conn: sqlite3.Connection) -> None:
    """
    The scraped matches themselves. Until now they only existed as
    spesen_data.json in the session folders; from here on they are the
    source of truth.

    Two design decisions that are not obvious:

    1. `match_key` instead of a natural key made of the columns.
       DFBnet does not (yet) supply a match number, so the identity is
       home + away + date. As soon as the match number is available, it
       simply becomes the new match_key - foreign keys on `matches.id` stay
       untouched. Tournament fixtures without teams get a key made of venue
       and kick-off, otherwise several tournaments on the same day would
       collide.

    2. `match_officials` is a snapshot per match, not a table of persons.
       Two referees can have the same name, and an address change in the
       middle of the season must not retroactively change the address in an
       already submitted expense claim.

    For the same reason the expense rates and the km rate are frozen at
    scrape time instead of being recomputed on every render.
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
    Replaces the metadata.json in the session folder. The scraper runs in its
    own process (Playwright does not get along with the asyncio loop), used
    to write its progress to that file, and the API read it back for the
    2-second poll. This row is now the channel.

    error_code still carries the values the frontend checks for
    (DFB_CREDENTIALS_INVALID sends the user to the settings).
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
    Downloads are attached to a match from now on, no longer to a session.

    SQLite cannot remove NOT NULL from a column after the fact, so the table
    is rebuilt and the existing rows are carried over. The old rows keep their
    session_id and get no match_id - they are history.
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
    Pulls the matches from the existing session folders into the database.

    Until now they existed exclusively as spesen_data.json under
    <DATA_DIR>/output/session_*/. Without this step, on the day of the
    switchover every user's complete match history would have disappeared
    from the dashboard, because the old read path re-read the folders on
    every call.

    The folders are processed in ascending order of age so that for matches
    scraped several times the most recently seen state wins - the same rule
    the old endpoint applied at runtime (rescheduled kick-off times do occur
    in the data).

    Afterwards the already recorded travel costs are re-attached from the old
    table match_expenses to the new rows. The old table stays for now - it is
    the fallback in case something goes wrong here.

    The helpers are imported from the application code instead of copied
    here: the match_key MUST be built exactly as in the nightly scrape,
    otherwise the first run after the switchover creates everything twice.
    """
    # Local imports: db.matches imports db.database, which in turn imports this
    # module - at module level that would be a circular import.
    from core import config
    from db.matches import build_match_key, upsert_match
    from generator.spesen_calculator import calculate_spesen
    from utils.match_utils import extract_iso_date_from_anpfiff

    # Kilometre rate that applied at the time of this migration. Deliberately a
    # literal: a later change of the flat rate must not retroactively shift the
    # frozen values of historical claims.
    km_satz = 0.30

    # get_output_dir() instead of DATA_DIR/"output": an installation may have
    # OUTPUT_DIR set or still be on the old layout, and then the folders
    # were located elsewhere.
    output_dir = config.get_output_dir()

    besitzer = {
        row["session_id"]: row
        for row in conn.execute("SELECT session_id, user_id, created_at FROM sessions")
    }

    ordner = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: (besitzer[d.name]["created_at"] if d.name in besitzer else "", d.name),
    ) if output_dir.exists() else []

    # If the database knows sessions, their folders must be there too. If they
    # are gone, the path points elsewhere or cleanup happened too early. Without
    # this check the step would pass, migration 007 would drop `sessions`
    # right after, and the history of all users would be lost without a single
    # error message.
    #
    # What is checked is the number of folders FOUND AGAIN, not merely whether
    # the directory exists: an "rm -rf data/output/*" leaves the directory in
    # place and would otherwise have slipped through.
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
        # A few sessions without a folder are normal: runs that already failed at
        # the DFB login never wrote anything. Only when a substantial part is
        # missing is that a sign of a problem.
        melden = logger.warning if fehlend > len(besitzer) // 10 else logger.info
        melden(
            f"{fehlend} von {len(besitzer)} Sessions haben keinen Ordner "
            "(in der Regel Laeufe, die vor dem Scrapen abgebrochen sind)."
        )

    spiele = uebersprungen = ohne_besitzer = 0

    for verzeichnis in ordner:
        session = besitzer.get(verzeichnis.name)
        if not session:
            # Folder without a database row - nobody can own it
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

    # Re-attach recorded travel costs to the new rows. The old key was
    # (user_id, heim_team, gast_team, datum) - exactly the fields that also
    # make up the match_key for matches with teams.
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
    Clears away the tables that nobody has touched since the switch to
    database-backed matches.

    `sessions` described a folder under data/output that no longer exists.
    `match_expenses` was the flat predecessor of `official_expenses` with
    exactly three fixed roles per match.

    Both were read one last time in migration 006. After that they are dead -
    there is not a single access left in the code. Should the backfill turn
    out to have gone wrong after all, the fallback is the backup copy the
    runner places next to app.db before every run.

    `download_log.session_id` stays: the column carries the download history
    from the time before the switchover.
    """
    _run_script(conn, """
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS match_expenses;
    """)


def _migration_008_rekey_matches(conn: sqlite3.Connection) -> None:
    """
    Recomputes match_key for existing rows according to the extended rule.

    The key now also contains team type and league. Without this step the
    next scrape would form new keys, not find the existing rows again and
    create every match a second time - including losing the link to the
    entered kilometres.

    Additional components can only separate, never merge, so no conflict
    with UNIQUE(user_id, match_key) can arise.

    What this step can NOT do: bring back a fixture that was previously
    overwritten by another one. It shows up as its own row on the next
    scrape.
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


def _migration_009_stammdaten(conn: sqlite3.Connection) -> None:
    """
    The referee's own master data from DFBnet.

    DFBnet keeps this data on the referee account, and every app user stores
    exactly one such account - so exactly one row belongs to a user.
    That is why user_id is the primary key here: it is foreign key and
    UNIQUE in one and makes a second row per user impossible.

    Deliberately a separate table instead of further columns on users:
    get_user_by_id does a SELECT *, and its result hangs off get_current_user
    in every protected endpoint. Address and date of birth have no business
    being there.

    All scrape fields are NOT NULL DEFAULT '' because the upsert merges away
    empty values via COALESCE(NULLIF(...)) - '' means "the scraper delivered
    nothing", not "the field is now empty". The personal fields are stored
    encrypted (see db/stammdaten.py), the schema does not see that: in both
    cases it is TEXT.
    """
    _run_script(conn, """
        CREATE TABLE stammdaten (
            user_id INTEGER PRIMARY KEY,
            name_vorname TEXT NOT NULL DEFAULT '',
            strasse TEXT NOT NULL DEFAULT '',
            plz_ort TEXT NOT NULL DEFAULT '',
            geburtsdatum TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            telefon_privat TEXT NOT NULL DEFAULT '',
            telefon_geschaeftlich TEXT NOT NULL DEFAULT '',
            telefon_mobil TEXT NOT NULL DEFAULT '',
            ausweisnummer TEXT NOT NULL DEFAULT '',
            ausweisgueltigkeit TEXT NOT NULL DEFAULT '',
            foto_status TEXT NOT NULL DEFAULT '',
            foto_gueltigkeit TEXT NOT NULL DEFAULT '',
            sr_gebiet TEXT NOT NULL DEFAULT '',
            schiedsrichter_seit TEXT NOT NULL DEFAULT '',
            verein TEXT NOT NULL DEFAULT '',
            fehlmonate TEXT NOT NULL DEFAULT '',
            zusatzausbildungen TEXT NOT NULL DEFAULT '',
            patensystem_am TEXT NOT NULL DEFAULT '',
            kreditor_nr TEXT NOT NULL DEFAULT '',
            debitor_nr TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            umsatzsteuerpflichtig TEXT NOT NULL DEFAULT '',
            fussball_de_hinweis TEXT NOT NULL DEFAULT '',
            bemerkung TEXT NOT NULL DEFAULT '',
            qmax_sr TEXT NOT NULL DEFAULT '',
            qmax_sra1 TEXT NOT NULL DEFAULT '',
            qmax_sra2 TEXT NOT NULL DEFAULT '',
            qmax_beobachter TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)

def _migration_010_saison(conn: sqlite3.Connection) -> None:
    """
    Officiated matches and season summary from the "Matches & Statistics" tab.

    Deliberately completely separate from `matches`. That holds the
    FIXTURES, to which the kilometres entered by the user are attached; this
    holds the OFFICIATED matches with result and card statistics. Partly the
    same fixture, but from two different tables of DFBnet. Merging them via
    home/away/date would go wrong with tournaments and rescheduling and, in
    the worst case, attach recorded travel costs to the wrong row.

    Unlike with `matches`, everything may be rewritten per season here: nothing
    on these rows was entered by the user. That is also necessary, because
    DFBnet corrects results and card counts after the fact, and the current
    season grows with every matchday.

    The card columns are INTEGER and may be NULL - DFBnet shows a "-" in the
    table when nothing was recorded for a match. As text, sums over a season
    would not be possible.
    """
    _run_script(conn, """
        CREATE TABLE season_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            saison TEXT NOT NULL,
            match_key TEXT NOT NULL,
            datum TEXT NOT NULL,
            uhrzeit TEXT NOT NULL DEFAULT '',
            liga TEXT NOT NULL DEFAULT '',
            heim TEXT NOT NULL DEFAULT '',
            gast TEXT NOT NULL DEFAULT '',
            ergebnis TEXT NOT NULL DEFAULT '',
            heim_gelb INTEGER,
            heim_gelbrot INTEGER,
            heim_rot INTEGER,
            gast_gelb INTEGER,
            gast_gelbrot INTEGER,
            gast_rot INTEGER,
            eigene_rolle TEXT NOT NULL DEFAULT '',
            scraped_at TEXT NOT NULL,
            UNIQUE (user_id, saison, match_key),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE INDEX idx_season_matches_user ON season_matches (user_id, saison, datum DESC);

        CREATE TABLE season_match_officials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_match_id INTEGER NOT NULL,
            rolle TEXT NOT NULL,
            seq INTEGER NOT NULL DEFAULT 0,
            name TEXT NOT NULL DEFAULT '',
            ist_selbst INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (season_match_id) REFERENCES season_matches (id) ON DELETE CASCADE
        );

        CREATE INDEX idx_season_match_officials_match ON season_match_officials (season_match_id);

        CREATE TABLE season_appearances (
            user_id INTEGER NOT NULL,
            saison TEXT NOT NULL,
            rolle TEXT NOT NULL,
            seq INTEGER NOT NULL DEFAULT 0,
            geleitet TEXT NOT NULL DEFAULT '',
            zurueckgegeben TEXT NOT NULL DEFAULT '',
            nicht_angetreten TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (user_id, saison, rolle),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE season_education (
            user_id INTEGER NOT NULL,
            saison TEXT NOT NULL,
            lehrabend TEXT NOT NULL DEFAULT '',
            lehrabend_online TEXT NOT NULL DEFAULT '',
            leistungspruefung TEXT NOT NULL DEFAULT '',
            scraped_at TEXT NOT NULL,
            PRIMARY KEY (user_id, saison),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)

def _migration_011_saison_vollstaendig(conn: sqlite3.Connection) -> None:
    """
    Remembers per season whether it was read completely.

    Finished seasons no longer change at DFBnet. Re-reading them every night
    costs, with nine seasons, a multiple of the actual work - the retrieval
    is bound by switching steps, not by computing time. In future a season is
    only read if it is the current one or its data is incomplete.

    spiele_erwartet is the hit count reported by DFBnet. When checking, it is
    held against the rows actually stored: if the two do not match,
    something is missing and the season is re-read completely.

    Existing rows get vollstaendig = 0 and are thereby re-read exactly once -
    their completeness cannot be determined retroactively.
    """
    _run_script(conn, """
        ALTER TABLE season_education ADD COLUMN spiele_erwartet INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE season_education ADD COLUMN vollstaendig INTEGER NOT NULL DEFAULT 0;
    """)

def _migration_012_geocode_cache(conn: sqlite3.Connection) -> None:
    """
    Cache for address -> coordinate.

    The map in the travel costs tab needs longitude and latitude, but DFBnet
    only supplies plain-text addresses. When needed they are looked up once at
    the geocoder and then kept here: the same venue and the same colleagues
    keep showing up over a season, and the public Nominatim service must not
    be queried in series.

    Two design decisions:

    1. The key contains the provider. Anyone who later configures their own
       geocoder gets its results - and not those of the previous service,
       which may differ.

    2. A failure is recorded as a row with lat/lon NULL. Without it, every
       call of the map would run into the same unsuccessful request again.
       It is still searched again at some point: the geocoder may know the
       address later (see MISS_GUELTIG_TAGE in the geocoder).
    """
    _run_script(conn, """
        CREATE TABLE geocode_cache (
            anfrage TEXT NOT NULL,
            provider TEXT NOT NULL,
            lat REAL,
            lon REAL,
            resolved_at TEXT NOT NULL,
            PRIMARY KEY (anfrage, provider)
        );
    """)


def _migration_013_alte_herren_saetze(conn: sqlite3.Connection) -> None:
    """
    Corrects the frozen expense rates of the Alte Herren matches.

    The rates are frozen at scrape time so that a later change of the
    expense regulations does not retroactively rewrite an already submitted
    claim. This step rewrites them anyway - but not because of a changed
    regulation, rather because the calculator did not recognise the Alte
    Herren at all: it searched for the words "Alte Herren", but DFBnet
    delivers "Herren Ue32" to "Herren Ue50".

    As a result all Ue matches went through the men's table. A Kreisoberliga
    Ue45 received its 30/25 instead of the 25/23 from the "Kreis Alte Herren"
    row, and the Alte Herren state championships (40/30) found no rate at
    all. A wrong frozen value is not a state worth protecting, so exactly
    these rows are recalculated - all others stay untouched.
    """
    from generator.spesen_calculator import calculate_spesen, is_alte_herren

    geaendert = 0

    for row in conn.execute(
        "SELECT id, spielklasse, mannschaftsart, staffel, sr_spesen, sra_spesen FROM matches"
    ).fetchall():
        if not is_alte_herren((row["mannschaftsart"] or "").lower()):
            continue

        sr, sra = calculate_spesen(
            row["spielklasse"] or "", row["mannschaftsart"] or "", row["staffel"] or ""
        )
        if (sr, sra) == (row["sr_spesen"], row["sra_spesen"]):
            continue

        conn.execute(
            "UPDATE matches SET sr_spesen = ?, sra_spesen = ? WHERE id = ?",
            (sr, sra, row["id"]),
        )
        geaendert += 1
        logger.info(
            f"Spiel {row['id']} ({row['mannschaftsart']}, {row['spielklasse']}): "
            f"{row['sr_spesen']}/{row['sra_spesen']} -> {sr}/{sra}"
        )

    logger.info(f"Alt-Herren-Saetze korrigiert: {geaendert} Spiele")


def _migration_014_pokal_freundschaft_saetze(conn: sqlite3.Connection) -> None:
    """
    Deletes the frozen league-match rates of cup and friendly matches.

    Until now the calculator gave every match a rate from the league-match
    table, even a Kreispokal or Kreisfreundschaftsspiel. That this never
    ended up on paper was solely because the display and the generator each
    separately checked again whether a league match was involved - the wrong
    value was in the database regardless.

    This check is dropped now because the calculator decides itself. The old
    values would then suddenly be printed, and wrongly: under §2 para. 3 the
    cup rate depends on the highest-ranked team involved, under para. 4 the
    friendly rate depends on the league of the host. A Kreispokal match
    between two Kreisoberliga teams costs 30/25, not the 25/23 frozen here.

    Only what the calculator can still vouch for today is recalculated -
    women's youth and Alte Herren at district level, whose rate the
    regulations set independently of the league. The rest is emptied. League
    matches stay untouched: there the freezing protects an already submitted
    claim.
    """
    from generator.spesen_calculator import PUNKTSPIEL, calculate_spesen, wettbewerbsart

    geleert = gesetzt = 0

    for row in conn.execute(
        "SELECT id, spielklasse, mannschaftsart, staffel, sr_spesen, sra_spesen FROM matches"
    ).fetchall():
        if wettbewerbsart(row["spielklasse"] or "") == PUNKTSPIEL:
            continue

        sr, sra = calculate_spesen(
            row["spielklasse"] or "", row["mannschaftsart"] or "", row["staffel"] or ""
        )
        if (sr, sra) == (row["sr_spesen"], row["sra_spesen"]):
            continue

        conn.execute(
            "UPDATE matches SET sr_spesen = ?, sra_spesen = ? WHERE id = ?",
            (sr, sra, row["id"]),
        )
        if sr is None:
            geleert += 1
        else:
            gesetzt += 1

    logger.info(
        f"Pokal-/Freundschaftsspiele: {geleert} Saetze geleert, {gesetzt} neu gesetzt"
    )


def _migration_015_fremde_verbaende(conn: sqlite3.Connection) -> None:
    """
    Takes the TFV rates away again from matches of other regional associations.

    Until now the calculator only saw league and team type. But DFBnet
    normalises the league across association borders: a Kreisoberliga match
    in the Altmark appears there as "Kreisoberliga" just like any Thuringian
    one, an NOFV match of the C-juniors as "Landesliga". Matches of the
    neighbouring associations thus got the TFV's rates, although under §2
    para. 6 the hosting association pays by its own flat rates.

    This is only recognisable from the group ("1. Altmark West Liga",
    "U14-Talente-Spielrunde-Nordost"), which the calculator now receives.
    Here the affected rows are brought up to date - as in migration 013, a
    wrong frozen value is not a state worth protecting.
    """
    from generator.spesen_calculator import calculate_spesen, _ist_fremder_verband

    geaendert = 0

    for row in conn.execute(
        "SELECT id, spielklasse, mannschaftsart, staffel, sr_spesen, sra_spesen FROM matches"
    ).fetchall():
        # Only matches of other associations. A TFV match keeps its once-frozen
        # rate, even if the regulations now pay differently.
        if not _ist_fremder_verband(row["staffel"] or ""):
            continue

        sr, sra = calculate_spesen(
            row["spielklasse"] or "", row["mannschaftsart"] or "", row["staffel"] or ""
        )
        if (sr, sra) == (row["sr_spesen"], row["sra_spesen"]):
            continue

        conn.execute(
            "UPDATE matches SET sr_spesen = ?, sra_spesen = ? WHERE id = ?",
            (sr, sra, row["id"]),
        )
        geaendert += 1
        logger.info(
            f"Spiel {row['id']} ({row['mannschaftsart']}, {row['spielklasse']}, "
            f"{row['staffel']}): {row['sr_spesen']}/{row['sra_spesen']} -> {sr}/{sra}"
        )

    logger.info(f"Spiele fremder Verbände korrigiert: {geaendert}")


def _migration_016_ligen(conn: sqlite3.Connection) -> None:
    """
    The Thuringian men's leagues and their tables.

    For cup and friendly matches the expense rate depends on the league of the
    clubs involved (§2 para. 3 and 4), not on that of the match - but the
    fixture only says "Kreispokal". These tables close the gap; they are
    filled nightly from fussball.de and incidentally feed the *Leagues* tab.

    Two design decisions:

    1. kern and nummer are separate columns alongside, not an expression in
       the SELECT. Only that way can an index be put on them, and only that
       way is the matching rule fixed in exactly one place (see
       db.ligen.finde_mannschaft).

    2. The key is the team_id from fussball.de, not the name. A team can be
       renamed during the season - then its row should be replaced and not
       duplicated.
    """
    _run_script(conn, """
        CREATE TABLE liga_staffeln (
            staffel_id TEXT PRIMARY KEY,
            pfad TEXT NOT NULL,
            spielklasse TEXT NOT NULL,
            verband TEXT NOT NULL,
            anzeigename TEXT NOT NULL,
            rang INTEGER NOT NULL,
            aktualisiert_at TEXT NOT NULL
        );

        CREATE TABLE liga_tabellen (
            staffel_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            platz INTEGER NOT NULL,
            mannschaft TEXT NOT NULL,
            kern TEXT NOT NULL,
            nummer INTEGER NOT NULL,
            spiele INTEGER NOT NULL,
            siege INTEGER NOT NULL,
            unentschieden INTEGER NOT NULL,
            niederlagen INTEGER NOT NULL,
            tore INTEGER NOT NULL,
            gegentore INTEGER NOT NULL,
            punkte INTEGER NOT NULL,
            PRIMARY KEY (staffel_id, team_id),
            FOREIGN KEY (staffel_id) REFERENCES liga_staffeln (staffel_id) ON DELETE CASCADE
        );

        CREATE INDEX idx_liga_tabellen_zuordnung ON liga_tabellen (kern, nummer);
    """)


def _migration_017_beobachtungen(conn: sqlite3.Connection) -> None:
    """
    The own observations from Schiri-Beobachtung and Schiri-Portal.

    quelle separates the two modules: "herren" (regional association) and
    "portal" (DFB youth). Each has its own average per season and they must
    never be added together.

    Per match only the OWN grade is stored, together with the role in which
    it was given. The colleagues' grades are none of the business of anyone
    who is not a user themselves.

    beobachtung_saisons remembers which seasons were read completely - the
    empty ones too. Otherwise "without observation" could not be told apart
    from "never read", and every empty season would be queried again every
    night.
    """
    _run_script(conn, """
        CREATE TABLE beobachtungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quelle TEXT NOT NULL,
            saison TEXT NOT NULL,
            datum TEXT NOT NULL,
            uhrzeit TEXT NOT NULL DEFAULT '',
            spieltag TEXT NOT NULL DEFAULT '',
            staffel TEXT NOT NULL DEFAULT '',
            heim TEXT NOT NULL DEFAULT '',
            gast TEXT NOT NULL DEFAULT '',
            ergebnis TEXT NOT NULL DEFAULT '',
            rolle TEXT NOT NULL,
            note REAL NOT NULL,
            note_text TEXT NOT NULL DEFAULT '',
            beobachter TEXT NOT NULL DEFAULT '',
            freigegeben_am TEXT NOT NULL DEFAULT '',
            scraped_at TEXT NOT NULL,
            UNIQUE (user_id, quelle, saison, datum, uhrzeit, heim, gast, rolle),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE INDEX idx_beobachtungen_user ON beobachtungen (user_id, saison, quelle);

        CREATE TABLE beobachtung_saisons (
            user_id INTEGER NOT NULL,
            quelle TEXT NOT NULL,
            saison TEXT NOT NULL,
            anzahl INTEGER NOT NULL DEFAULT 0,
            scraped_at TEXT NOT NULL,
            PRIMARY KEY (user_id, quelle, saison),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)


def _migration_018_nofv_saetze(conn: sqlite3.Connection) -> None:
    """
    Fills in the rate for competitive matches of the NOFV leagues.

    Until now the calculator left every match above the TFV empty, and that
    is how it was frozen. Now it knows the rates of the NOFV finance
    regulations (§9 no. 7) for Regionalliga and Oberliga.

    Only rows WITHOUT a rate that the calculator recognises as an NOFV
    competitive match are touched. An empty field was never a settled state
    to be protected - whoever has claimed so far entered the amount by hand.
    """
    from generator.spesen_calculator import SPESEN_NOFV, nofv_spielklasse

    ergaenzt = 0

    for row in conn.execute(
        "SELECT id, spielklasse, mannschaftsart, staffel FROM matches WHERE sr_spesen IS NULL"
    ).fetchall():
        nofv = nofv_spielklasse(
            row["spielklasse"] or "", row["mannschaftsart"] or "", row["staffel"] or ""
        )
        if not nofv:
            continue

        sr, sra = SPESEN_NOFV[nofv]
        conn.execute(
            "UPDATE matches SET sr_spesen = ?, sra_spesen = ? WHERE id = ?",
            (sr, sra, row["id"]),
        )
        ergaenzt += 1

    logger.info(f"NOFV-Saetze nachgetragen: {ergaenzt} Spiele")


def _migration_019_spielberichte(conn: sqlite3.Connection) -> None:
    """
    The match reports of the own matches from "Spielberichte -> Einsatzplan".

    The key is the match ID that DFBnet carries in the link to the report -
    it is stable across seasons and rescheduling. With the officiated matches
    (season_matches) and the fixtures (matches) the link is made when reading
    via date and teams, not via foreign key: both tables are replaced or
    re-keyed independently of this.

    daten holds the processed course of the match as JSON (events, line-ups,
    checks, confirmations). It is only displayed, never evaluated; a table
    per event type would be mere ballast here.

    fahrtkosten and spesen are the totals for the whole crew, as DFBnet lists
    them in the report. They are separate columns because the expenses page
    shows them per match without loading the whole report.

    The documents are files under DATA_DIR/spielberichte/<user>/; pfad is
    relative to DATA_DIR so that a relocated data folder stays valid.

    spielbericht_saisons remembers which seasons have been read completely -
    finished and without a report still waiting for its release.
    """
    _run_script(conn, """
        CREATE TABLE spielberichte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            dfb_spiel_id TEXT NOT NULL,
            saison TEXT NOT NULL,
            datum TEXT NOT NULL,
            uhrzeit TEXT NOT NULL DEFAULT '',
            gruppe TEXT NOT NULL DEFAULT '',
            spielnummer TEXT NOT NULL DEFAULT '',
            spielkennung TEXT NOT NULL DEFAULT '',
            heim TEXT NOT NULL DEFAULT '',
            gast TEXT NOT NULL DEFAULT '',
            ergebnis TEXT NOT NULL DEFAULT '',
            fahrtkosten REAL,
            spesen REAL,
            daten TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            UNIQUE (user_id, dfb_spiel_id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE INDEX idx_spielberichte_user_datum ON spielberichte (user_id, datum);

        CREATE TABLE spielbericht_dokumente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spielbericht_id INTEGER NOT NULL,
            dfb_dokument_id TEXT NOT NULL,
            kategorie TEXT NOT NULL DEFAULT '',
            dateiname TEXT NOT NULL,
            beschreibung TEXT NOT NULL DEFAULT '',
            hochgeladen_von TEXT NOT NULL DEFAULT '',
            hochgeladen_am TEXT NOT NULL DEFAULT '',
            groesse INTEGER NOT NULL DEFAULT 0,
            pfad TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            UNIQUE (spielbericht_id, dfb_dokument_id),
            FOREIGN KEY (spielbericht_id) REFERENCES spielberichte (id) ON DELETE CASCADE
        );

        CREATE TABLE spielbericht_saisons (
            user_id INTEGER NOT NULL,
            saison TEXT NOT NULL,
            anzahl INTEGER NOT NULL DEFAULT 0,
            fertig INTEGER NOT NULL DEFAULT 0,
            scraped_at TEXT NOT NULL,
            PRIMARY KEY (user_id, saison),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)


def _migration_020_spielbericht_log(conn: sqlite3.Connection) -> None:
    """
    Logs how the match reports are used - like login_log and download_log
    for the usage statistics.

    aktion: "ansehen" (report opened), "dokument_oeffnen" or
    "dokument_laden". quelle says where the report was opened from
    ("saison", "spesen" or "direkt" for a call without origin, such as an
    external link; for documents "bericht").

    No foreign key on spielberichte: the log is history and should outlive a
    deleted report (account change).
    """
    _run_script(conn, """
        CREATE TABLE spielbericht_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            spielbericht_id INTEGER NOT NULL,
            dokument_id INTEGER,
            aktion TEXT NOT NULL,
            quelle TEXT NOT NULL DEFAULT 'direkt',
            geklickt_am TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE INDEX idx_spielbericht_log_user ON spielbericht_log (user_id, geklickt_am DESC);
    """)


def _migration_021_login_sperren(conn: sqlite3.Connection) -> None:
    """
    Counts failed logins per e-mail address so that a lockout takes effect
    after five failed attempts.

    Deliberately by address and not by IP: the instance sits behind a
    Cloudflare Tunnel, all requests come from the same address there - an IP
    lockout would lock everyone out. Addresses without an account are
    counted too, otherwise the lockout would reveal which addresses are
    registered. No foreign key on users for the same reason.
    """
    _run_script(conn, """
        CREATE TABLE login_sperren (
            email TEXT PRIMARY KEY,
            fehlversuche INTEGER NOT NULL DEFAULT 0,
            letzter_fehlversuch TEXT NOT NULL,
            gesperrt_bis TEXT
        );
    """)


def _migration_022_dfb_login_abgelehnt(conn: sqlite3.Connection) -> None:
    """
    Remembers since when DFBnet has been rejecting the stored credentials.

    Until now this was only in the last retrieval. The next run - or an
    aborted one - overwrote it, and the notice disappeared although the
    credentials were still wrong. NULL means: last accepted or not yet
    checked.
    """
    _run_script(conn, """
        ALTER TABLE users ADD COLUMN dfb_login_abgelehnt_seit TEXT;
    """)


def _migration_023_dfb_spiel_id(conn: sqlite3.Connection) -> None:
    """
    The DFBnet ID becomes the identity of a match.

    Since the fixtures are read via the JSON interface, each match comes with
    its ID - the same one under which the match report is filed
    (spielberichte.dfb_spiel_id). With it a rescheduled match stays in its
    row instead of appearing as a new one.

    Existing matches get their ID here from the stored match reports (same
    user, same day, both teams or one team plus kick-off time - as when
    linking the reports in the list), plus the match identifier for the
    expense receipts. What has no report - above all future matches - is
    assigned by the next retrieval via the match_key
    (db.matches._schreibe_mit_id).

    Ambiguous cases stay without an ID: better to assign later than wrongly.
    """
    _run_script(conn, """
        ALTER TABLE matches ADD COLUMN dfb_spiel_id TEXT;
    """)

    # Own copy of the mapping from db.spielberichte (team_kern, Zuordnung):
    # a migration must not change along with later changes to the code.
    # The names are spelled differently in the DFBnet modules
    # ("Hertha BSC II" / "Hertha BSC U23", "... 1911" / "... 1911 e.V.").
    zusatz = re.compile(r"^(u\d{1,2}|i{1,3}|iv|\d{1,2}|e|v|ev)$")

    def kern(name):
        text = (name or "").replace("\u00ad", "").casefold()
        return "".join(w for w in re.split(r"[\W_]+", text) if w and not zusatz.match(w))

    def gleich(a, b):
        ka, kb = kern(a), kern(b)
        if not ka or not kb:
            return False
        kurz, lang = sorted((ka, kb), key=len)
        return ka == kb or (len(kurz) >= 8 and kurz in lang)

    def zeit(text):
        t = re.search(r"(\d{1,2}):(\d{2})", text or "")
        return f"{int(t.group(1)):02d}:{t.group(2)}" if t else ""

    spiele = {}
    for match_id, user_id, datum, heim, gast, anpfiff in conn.execute(
        "SELECT id, user_id, datum, heim_team, gast_team, anpfiff FROM matches "
        "WHERE heim_team <> '' AND gast_team <> ''"
    ):
        spiele.setdefault((user_id, datum), []).append((match_id, heim, gast, zeit(anpfiff)))

    belegt_spiel, belegt_id = set(), set()
    zugeordnet = 0
    for user_id, spiel_id, datum, uhrzeit, heim, gast, kennung in conn.execute(
        "SELECT user_id, dfb_spiel_id, datum, uhrzeit, heim, gast, spielkennung FROM spielberichte"
    ).fetchall():
        kandidaten = [k for k in spiele.get((user_id, datum), []) if k[0] not in belegt_spiel]
        beide = [k for k in kandidaten if gleich(k[1], heim) and gleich(k[2], gast)]
        zur_zeit = [k for k in kandidaten if uhrzeit and k[3] == zeit(uhrzeit)]
        if len(beide) > 1:
            beide = [k for k in beide if k in zur_zeit]
        if not beide:
            beide = [k for k in zur_zeit if gleich(k[1], heim) or gleich(k[2], gast)]
        if len(beide) != 1 or (user_id, spiel_id) in belegt_id:
            continue

        belegt_spiel.add(beide[0][0])
        belegt_id.add((user_id, spiel_id))
        zugeordnet += conn.execute(
            "UPDATE matches SET dfb_spiel_id = ?, spielnummer = COALESCE(NULLIF(?, ''), spielnummer) "
            "WHERE id = ? AND dfb_spiel_id IS NULL",
            (spiel_id, kennung or "", beide[0][0]),
        ).rowcount

    _run_script(conn, """
        CREATE UNIQUE INDEX idx_matches_user_dfb_spiel_id
            ON matches (user_id, dfb_spiel_id) WHERE dfb_spiel_id IS NOT NULL;
    """)
    logger.info(f"DFBnet-ID aus Spielberichten zugeordnet: {zugeordnet} Spiele")


# (version, description, function) - ascending, gaps are not allowed.
def _migration_024_platz_und_eigene_rolle(conn: sqlite3.Connection) -> None:
    """
    Coordinates of the venue and the own role per match.

    The fixtures interface supplies latitude and longitude for every venue -
    more precise than the address search, which can only guess at
    "Auenweg, 07318 Saalfeld" without a house number. Kilometre suggestions,
    statistics and the map of visited venues calculate with it.

    ist_selbst marks the user's row in the crew (their referee ID appears in
    the fixture). Without it one could not tell whether the SR or the SRA
    expenses are the user's own. Existing matches get both on the next
    retrieval, which reads the whole season.
    """
    _run_script(conn, """
        ALTER TABLE matches ADD COLUMN staette_lat REAL;
        ALTER TABLE matches ADD COLUMN staette_lon REAL;
        ALTER TABLE match_officials ADD COLUMN ist_selbst INTEGER NOT NULL DEFAULT 0;
    """)


def _migration_025_strecken_cache(conn: sqlite3.Connection) -> None:
    """
    Cache for road distances between two coordinates.

    Kilometre suggestions and the estimated travel costs of the statistics
    query a routing service. The public service of OpenStreetMap Germany
    allows one request per second; but the same routes (home -> home ground
    of the neighbouring club) keep repeating. Each route is therefore asked
    for once and then kept here.

    The coordinates are rounded to four decimals in the key (a little over
    ten metres): no road distance distinguishes more finely. The direction
    counts - one-way streets make the outward and return journey different.
    meter NULL means "the service knows no route", as with the geocoder.
    """
    _run_script(conn, """
        CREATE TABLE strecken_cache (
            von_lat REAL NOT NULL,
            von_lon REAL NOT NULL,
            nach_lat REAL NOT NULL,
            nach_lon REAL NOT NULL,
            provider TEXT NOT NULL,
            meter REAL,
            resolved_at TEXT NOT NULL,
            PRIMARY KEY (von_lat, von_lon, nach_lat, nach_lon, provider)
        );
    """)


def _migration_026_ortsnamen_cache(conn: sqlite3.Connection) -> None:
    """
    Cache for the place name around a coordinate (reverse geocoding).

    Mileage suggestions may propose meeting somewhere on the way. A bare
    coordinate means nothing to a referee, "near Kahla" does - so the
    meeting point is looked up once at the geocoder and kept here. The key
    is rounded to three decimals (about a hundred metres); the name is that
    of the village or town, not of a street. name NULL means "nothing
    found", like in geocode_cache.
    """
    _run_script(conn, """
        CREATE TABLE ortsnamen_cache (
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            provider TEXT NOT NULL,
            name TEXT,
            resolved_at TEXT NOT NULL,
            PRIMARY KEY (lat, lon, provider)
        );
    """)


MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "baseline schema", _migration_001_baseline),
    (2, "wal journal mode", _migration_002_wal),
    (3, "matches, officials and expenses", _migration_003_matches),
    (4, "scrape runs replace session metadata", _migration_004_scrape_runs),
    (5, "downloads reference matches", _migration_005_download_log_matches),
    (6, "backfill matches from session folders", _migration_006_backfill_from_sessions),
    (7, "drop legacy session and expense tables", _migration_007_drop_legacy_tables),
    (8, "rekey matches by mannschaftsart and spielklasse", _migration_008_rekey_matches),
    (9, "referee coredata per user", _migration_009_stammdaten),
    (10, "officiated games and season totals", _migration_010_saison),
    (11, "track which seasons are completely stored", _migration_011_saison_vollstaendig),
    (12, "cache geocoded addresses for the match map", _migration_012_geocode_cache),
    (13, "refreeze expense rates for old boys matches", _migration_013_alte_herren_saetze),
    (14, "clear league rates frozen on cup and friendly matches", _migration_014_pokal_freundschaft_saetze),
    (15, "drop tfv rates from other associations matches", _migration_015_fremde_verbaende),
    (16, "thuringian league tables for cup and friendly rates", _migration_016_ligen),
    (17, "own observation grades per season", _migration_017_beobachtungen),
    (18, "nofv rates for regionalliga and oberliga league matches", _migration_018_nofv_saetze),
    (19, "match reports with events, expenses and documents", _migration_019_spielberichte),
    (20, "log how match reports and their documents are opened", _migration_020_spielbericht_log),
    (21, "lock the login after repeated failed attempts", _migration_021_login_sperren),
    (22, "remember since when dfbnet rejects the stored credentials", _migration_022_dfb_login_abgelehnt),
    (23, "identify matches by their dfbnet id", _migration_023_dfb_spiel_id),
    (24, "venue coordinates and the own role per match", _migration_024_platz_und_eigene_rolle),
    (25, "cache road distances for mileage suggestions", _migration_025_strecken_cache),
    (26, "cache place names of meeting points", _migration_026_ortsnamen_cache),
]


def _backup_database(conn: sqlite3.Connection, db_path: Path, from_version: int) -> Path | None:
    """
    Places a copy of the database next to the original file before migrating.
    Returns the path of the backup, or None if there is no database file yet
    (fresh installation - nothing to back up).

    Deliberately via SQLite's backup API and not via file copy: once the
    database runs in WAL mode (from migration 002), freshly committed data
    still sits in app.db-wal. A shutil.copy2 only takes app.db along and thus
    yields a silent partial backup - worthless exactly when it is needed.
    backup() takes a consistent snapshot including the WAL content.
    """
    if not db_path.exists():
        return None

    # sqlite3.connect creates the file as soon as it opens it. A file without
    # a single schema object is therefore also a fresh installation.
    if conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0:
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
    Brings the database up to date.

    Each step runs in its own transaction and sets user_version afterwards.
    If a step fails, it is rolled back completely, the database stays at the
    last successfully applied version and the exception is passed on - the
    app does not start half-migrated. A restart cleanly retries the failed
    step.

    Returns:
        The version the database is at after the run.
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
            # Explicit BEGIN: Python's sqlite3 does not open a transaction for DDL
            # on its own, and without one rollback() has no effect.
            # journal_mode does not tolerate an open transaction, hence the
            # exception for step 2.
            transaktional = migrate is not _migration_002_wal
            if transaktional:
                conn.execute("BEGIN")

            migrate(conn)

            # user_version does not accept parameter binding; the version
            # comes from MIGRATIONS and is therefore not foreign input.
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error(f"Migration {version} ({description}) fehlgeschlagen - Abbruch")
            raise

        current = version

    logger.info(f"Schema auf Version {current}")
    return current
