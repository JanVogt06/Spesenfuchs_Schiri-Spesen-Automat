"""
Schema migrations: fresh database, transactions, backups and the data
migrations that rewrite existing rows.

For the data migrations, a database is brought exactly to the predecessor
version, filled with rows there and then migrated further - just as it
happens on a real installation during an update.
"""
import json
import sqlite3
from datetime import datetime, UTC

import pytest

import db.database as database
import db.migrations as migrations
from db_helpers import (
    feste_uhr, migriere_bis, nutzer_anlegen, spiel, spiel_einfuegen, tabellen, user_version,
)


@pytest.fixture
def leere_db(tmp_path, monkeypatch):
    """A database path without a file - nothing migrated yet."""
    pfad = tmp_path / "app.db"
    monkeypatch.setattr(database, "DB_PATH", pfad)
    return pfad


def _letzte_version() -> int:
    return migrations.MIGRATIONS[-1][0]


def _backups(pfad):
    return sorted(p.name for p in pfad.parent.glob(f"{pfad.name}.v*.bak"))


def _conn():
    return database.get_connection()


# --------------------------------------------------------------- Structure


class TestMigrationsliste:
    def test_versionen_lueckenlos_ab_eins(self):
        versionen = [v for v, _, _ in migrations.MIGRATIONS]
        assert versionen == list(range(1, len(versionen) + 1))

    def test_jede_migration_hat_beschreibung_und_funktion(self):
        for version, beschreibung, funktion in migrations.MIGRATIONS:
            assert beschreibung.strip(), version
            assert callable(funktion), version

    def test_funktionen_eindeutig(self):
        funktionen = [f for _, _, f in migrations.MIGRATIONS]
        assert len(set(funktionen)) == len(funktionen)


# ------------------------------------------------------------- Fresh database


class TestFrischeDatenbank:
    def test_endet_auf_letzter_version(self, db):
        assert user_version() == _letzte_version()

    def test_alle_tabellen_da(self, db):
        erwartet = {
            "users", "login_log", "download_log", "matches", "match_officials",
            "official_expenses", "scrape_runs", "stammdaten", "season_matches",
            "season_match_officials", "season_appearances", "season_education",
            "geocode_cache", "liga_staffeln", "liga_tabellen", "beobachtungen",
            "beobachtung_saisons", "spielberichte", "spielbericht_dokumente",
            "spielbericht_saisons", "spielbericht_log", "login_sperren",
        }
        assert erwartet <= tabellen()

    def test_altlast_tabellen_weg(self, db):
        assert not {"sessions", "match_expenses", "download_log_neu"} & tabellen()

    def test_wal_aktiv(self, db):
        conn = _conn()
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        finally:
            conn.close()

    def test_spalten_aus_spaeteren_migrationen(self, db):
        conn = _conn()
        try:
            education = {r["name"] for r in conn.execute("PRAGMA table_info(season_education)")}
            download = {r["name"]: r for r in conn.execute("PRAGMA table_info(download_log)")}
        finally:
            conn.close()
        assert {"spiele_erwartet", "vollstaendig"} <= education
        # Migration 005: session_id may be empty, match_id is new
        assert "match_id" in download
        assert download["session_id"]["notnull"] == 0

    def test_zweiter_lauf_ist_noop(self, db):
        vorher = _backups(db)
        conn = _conn()
        try:
            assert migrations.apply_migrations(conn, db) == _letzte_version()
        finally:
            conn.close()
        assert _backups(db) == vorher

    def test_init_database_mehrfach(self, db):
        database.init_database()
        database.init_database()
        assert user_version() == _letzte_version()

    def test_frische_installation_ohne_backup(self, leere_db):
        database.init_database()
        assert _backups(leere_db) == []

    def test_backup_ohne_datei_gibt_none(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        try:
            assert migrations._backup_database(conn, tmp_path / "gibtsnicht.db", 0) is None
        finally:
            conn.close()
        assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ Backup


class TestBackup:
    def test_backup_beim_update_einer_bestehenden_datenbank(self, leere_db, monkeypatch):
        vorher = _letzte_version() - 1
        migriere_bis(monkeypatch, vorher)
        for alt in leere_db.parent.glob("*.bak"):
            alt.unlink()

        conn = _conn()
        nutzer_anlegen(conn, "vorher@example.org")
        conn.close()

        feste_uhr(monkeypatch, migrations, jetzt=datetime(2026, 11, 23, 4, 5, 6, tzinfo=UTC))
        database.init_database()

        assert _backups(leere_db) == [f"app.db.v{vorher}.20261123_040506.bak"]

        sicherung = sqlite3.connect(leere_db.parent / _backups(leere_db)[0])
        try:
            assert sicherung.execute("PRAGMA user_version").fetchone()[0] == vorher
            # Freshly committed data is in the WAL - the backup must contain it
            emails = [r[0] for r in sicherung.execute("SELECT email FROM users")]
            assert emails == ["vorher@example.org"]
        finally:
            sicherung.close()

    def test_kein_backup_ohne_ausstehende_migration(self, db):
        for alt in db.parent.glob("*.bak"):
            alt.unlink()
        database.init_database()
        assert _backups(db) == []


# ------------------------------------------------------------- Transactions


def _kaputte_migration(conn):
    conn.execute("CREATE TABLE halb_fertig (id INTEGER)")
    conn.execute("INSERT INTO halb_fertig VALUES (1)")
    conn.execute("UPDATE users SET email = 'veraendert@example.org'")
    raise RuntimeError("Abbruch mitten in der Migration")


def _heile_migration(conn):
    conn.execute("CREATE TABLE halb_fertig (id INTEGER)")


class TestTransaktion:
    def test_scheiternde_migration_rollt_zurueck(self, db, monkeypatch):
        ziel = _letzte_version()
        conn = _conn()
        nutzer_anlegen(conn, "bleibt@example.org")
        conn.close()

        monkeypatch.setattr(
            migrations, "MIGRATIONS",
            migrations.MIGRATIONS + [(ziel + 1, "kaputt", _kaputte_migration)],
        )
        with pytest.raises(RuntimeError, match="Abbruch"):
            database.init_database()

        assert user_version() == ziel
        assert "halb_fertig" not in tabellen()
        conn = _conn()
        try:
            assert [r["email"] for r in conn.execute("SELECT email FROM users")] == ["bleibt@example.org"]
        finally:
            conn.close()

    def test_neuer_start_holt_gescheiterten_schritt_nach(self, db, monkeypatch):
        ziel = _letzte_version()
        basis = migrations.MIGRATIONS

        monkeypatch.setattr(migrations, "MIGRATIONS", basis + [(ziel + 1, "kaputt", _kaputte_migration)])
        with pytest.raises(RuntimeError):
            database.init_database()

        monkeypatch.setattr(migrations, "MIGRATIONS", basis + [(ziel + 1, "repariert", _heile_migration)])
        database.init_database()

        assert user_version() == ziel + 1
        assert "halb_fertig" in tabellen()

    def test_abbruch_mitten_im_lauf_behaelt_vorherige_schritte(self, leere_db, monkeypatch):
        basis = migrations.MIGRATIONS
        monkeypatch.setattr(
            migrations, "MIGRATIONS",
            basis[:3] + [(4, "kaputt", _kaputte_migration)] + basis[4:],
        )
        with pytest.raises(RuntimeError):
            database.init_database()

        # Steps 1-3 are committed, 4 is rolled back, the rest never ran
        assert user_version() == 3
        vorhanden = tabellen()
        assert "matches" in vorhanden
        assert "halb_fertig" not in vorhanden
        assert "scrape_runs" not in vorhanden

    def test_ddl_einer_echten_migration_wird_zurueckgerollt(self, leere_db, monkeypatch):
        """A migration that fails after CREATE TABLE leaves no table behind."""
        migriere_bis(monkeypatch, 3)

        def scrape_runs_und_dann_fehler(conn):
            migrations._migration_004_scrape_runs(conn)
            raise RuntimeError("nach dem DDL")

        basis = migrations.MIGRATIONS
        monkeypatch.setattr(
            migrations, "MIGRATIONS", basis[:3] + [(4, basis[3][1], scrape_runs_und_dann_fehler)]
        )
        with pytest.raises(RuntimeError):
            database.init_database()

        assert user_version() == 3
        assert "scrape_runs" not in tabellen()

        # With the real list the start then runs through cleanly
        monkeypatch.setattr(migrations, "MIGRATIONS", basis)
        database.init_database()
        assert user_version() == _letzte_version()


# -------------------------------------------------------- Data migrations


class TestMigration005DownloadLog:
    def test_bestand_bleibt_mit_session_id(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 4)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        conn.execute("""
            INSERT INTO download_log (user_id, session_id, filename, file_type, downloaded_at)
            VALUES (?, 'session_alt', 'a.docx', 'docx', '2025-01-01T00:00:00')
        """, (uid,))
        conn.commit()
        conn.close()

        migriere_bis(monkeypatch, 5)

        conn = _conn()
        try:
            zeilen = [dict(r) for r in conn.execute("SELECT * FROM download_log")]
            # New rows without a session are now allowed
            conn.execute("""
                INSERT INTO download_log (user_id, match_id, filename, file_type, downloaded_at)
                VALUES (?, 7, 'b.docx', 'docx', '2025-01-02T00:00:00')
            """, (uid,))
        finally:
            conn.close()

        assert len(zeilen) == 1
        assert zeilen[0]["session_id"] == "session_alt"
        assert zeilen[0]["match_id"] is None
        assert zeilen[0]["filename"] == "a.docx"


class TestMigration006Backfill:
    def _sessions(self, conn, uid, *sessions):
        for session_id, erstellt in sessions:
            conn.execute(
                "INSERT INTO sessions (session_id, user_id, status, created_at) VALUES (?, ?, 'done', ?)",
                (session_id, uid, erstellt),
            )
        conn.commit()

    def test_spiele_und_fahrtkosten_werden_uebernommen(self, leere_db, tmp_path, monkeypatch):
        ausgabe = tmp_path / "output"
        monkeypatch.setenv("OUTPUT_DIR", str(ausgabe))
        migriere_bis(monkeypatch, 5)

        conn = _conn()
        uid = nutzer_anlegen(conn)
        self._sessions(conn, uid,
                       ("session_alt", "2025-11-01T08:00:00"),
                       ("session_neu", "2025-11-05T08:00:00"))
        conn.execute("""
            INSERT INTO match_expenses (user_id, heim_team, gast_team, datum, sr_km, sr_oevm,
                                        sra1_km, sra1_oevm, sra2_km, sra2_oevm, updated_at)
            VALUES (?, 'FC Heim', 'SV Gast', '2025-11-08', 42, 3.5, NULL, NULL, 17, NULL, '2025-11-09')
        """, (uid,))
        conn.commit()
        conn.close()

        # The same match in two sessions - the younger state (rescheduled) wins
        for name, zeit in (("session_alt", "13:00"), ("session_neu", "15:00")):
            ordner = ausgabe / name
            ordner.mkdir(parents=True)
            (ordner / "spesen_data.json").write_text(
                json.dumps([spiel(tag="2025-11-08", zeit=zeit)]), encoding="utf-8"
            )
        # A folder without a session row belongs to nobody and is skipped
        (ausgabe / "session_fremd").mkdir()
        (ausgabe / "session_fremd" / "spesen_data.json").write_text(
            json.dumps([spiel(heim="Fremd", tag="2025-11-08")]), encoding="utf-8"
        )

        database.init_database()

        conn = _conn()
        try:
            spiele = [dict(r) for r in conn.execute("SELECT * FROM matches")]
            kosten = {
                r["rolle"]: (r["km"], r["oevm"])
                for r in conn.execute("SELECT * FROM official_expenses")
            }
        finally:
            conn.close()

        assert len(spiele) == 1
        assert spiele[0]["user_id"] == uid
        assert "15:00" in spiele[0]["anpfiff"]
        assert spiele[0]["scraped_at"] == "2025-11-05T08:00:00"
        assert spiele[0]["first_seen_at"] == "2025-11-01T08:00:00"
        assert spiele[0]["km_satz"] == 0.30
        assert kosten == {"SR": (42, 3.5), "SRA 2": (17, None)}
        assert not {"sessions", "match_expenses"} & tabellen()

    def test_bricht_ab_wenn_alle_ordner_fehlen(self, leere_db, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.delenv("SKIP_SESSION_BACKFILL", raising=False)
        (tmp_path / "output").mkdir()
        migriere_bis(monkeypatch, 5)

        conn = _conn()
        self._sessions(conn, nutzer_anlegen(conn), ("session_weg", "2025-11-01T08:00:00"))
        conn.close()

        with pytest.raises(RuntimeError, match="Session-Ordner"):
            database.init_database()

        # Nothing lost: version and legacy tables are still there
        assert user_version() == 5
        assert {"sessions", "match_expenses"} <= tabellen()

    def test_skip_variable_erlaubt_den_verlust(self, leere_db, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
        migriere_bis(monkeypatch, 5)

        conn = _conn()
        self._sessions(conn, nutzer_anlegen(conn), ("session_weg", "2025-11-01T08:00:00"))
        conn.close()

        monkeypatch.setenv("SKIP_SESSION_BACKFILL", "1")
        database.init_database()
        assert user_version() == _letzte_version()


class TestMigration008Rekey:
    def test_schluessel_bekommt_mannschaftsart_und_spielklasse(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 7)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        mit_teams = spiel_einfuegen(
            conn, uid, "FC Heim|SV Gast|2025-11-08",
            heim_team="FC Heim", gast_team="SV Gast", mannschaftsart="Herren", spielklasse="Kreisliga",
        )
        turnier = spiel_einfuegen(
            conn, uid, "turnier|Halle|Sonntag · 09.11.2025 · 10:00 Uhr", datum="2025-11-09",
            anpfiff="Sonntag · 09.11.2025 · 10:00 Uhr", staette_name="Halle",
        )
        conn.close()

        migriere_bis(monkeypatch, 8)

        conn = _conn()
        try:
            keys = {r["id"]: r["match_key"] for r in conn.execute("SELECT id, match_key FROM matches")}
        finally:
            conn.close()
        assert keys[mit_teams] == "FC Heim|SV Gast|2025-11-08|Herren|Kreisliga"
        assert keys[turnier] == "turnier|Halle|Sonntag · 09.11.2025 · 10:00 Uhr"


class TestMigration011SaisonVollstaendig:
    def test_bestand_wird_einmal_nachgelesen(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 10)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        conn.execute(
            "INSERT INTO season_education (user_id, saison, scraped_at) VALUES (?, '24/25', 'x')", (uid,)
        )
        conn.commit()
        conn.close()

        migriere_bis(monkeypatch, 11)

        conn = _conn()
        try:
            zeile = conn.execute("SELECT * FROM season_education").fetchone()
        finally:
            conn.close()
        assert zeile["vollstaendig"] == 0
        assert zeile["spiele_erwartet"] == 0


def _saetze(conn):
    return {
        r["match_key"]: (r["sr_spesen"], r["sra_spesen"])
        for r in conn.execute("SELECT match_key, sr_spesen, sra_spesen FROM matches")
    }


class TestMigration013AlteHerren:
    def test_nur_alt_herren_saetze_werden_neu_gerechnet(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 12)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        spiel_einfuegen(conn, uid, "ah_falsch", mannschaftsart="Herren Ü45",
                        spielklasse="Kreisoberliga", sr_spesen=30.0, sra_spesen=25.0)
        spiel_einfuegen(conn, uid, "ah_richtig", mannschaftsart="Herren Ü35",
                        spielklasse="Kreisliga", sr_spesen=25.0, sra_spesen=23.0)
        # A men's match with a deviating frozen value stays as it is
        spiel_einfuegen(conn, uid, "herren", mannschaftsart="Herren",
                        spielklasse="Kreisoberliga", sr_spesen=99.0, sra_spesen=88.0)
        conn.close()

        migriere_bis(monkeypatch, 13)

        conn = _conn()
        try:
            saetze = _saetze(conn)
        finally:
            conn.close()
        assert saetze == {
            "ah_falsch": (25.0, 23.0),
            "ah_richtig": (25.0, 23.0),
            "herren": (99.0, 88.0),
        }


class TestMigration014PokalFreundschaft:
    def test_pokalsaetze_geleert_klassenunabhaengige_gesetzt(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 13)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        spiel_einfuegen(conn, uid, "kreispokal", mannschaftsart="Herren",
                        spielklasse="Kreispokal", sr_spesen=25.0, sra_spesen=23.0)
        spiel_einfuegen(conn, uid, "freundschaft", mannschaftsart="Herren",
                        spielklasse="Kreisfreundschaftsspiele", sr_spesen=25.0, sra_spesen=23.0)
        spiel_einfuegen(conn, uid, "juniorinnen", mannschaftsart="C-Juniorinnen",
                        spielklasse="Kreispokal", sr_spesen=None, sra_spesen=None)
        spiel_einfuegen(conn, uid, "punktspiel", mannschaftsart="Herren",
                        spielklasse="Kreisoberliga", sr_spesen=99.0, sra_spesen=88.0)
        conn.close()

        migriere_bis(monkeypatch, 14)

        conn = _conn()
        try:
            saetze = _saetze(conn)
        finally:
            conn.close()
        assert saetze == {
            "kreispokal": (None, None),
            "freundschaft": (None, None),
            "juniorinnen": (20.0, None),
            "punktspiel": (99.0, 88.0),
        }


class TestMigration015FremdeVerbaende:
    def _seed(self, monkeypatch):
        migriere_bis(monkeypatch, 14)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        spiel_einfuegen(conn, uid, "altmark", mannschaftsart="Herren", spielklasse="Kreisoberliga",
                        staffel="1. Altmark West Liga", sr_spesen=30.0, sra_spesen=25.0)
        spiel_einfuegen(conn, uid, "tfv_richtig", mannschaftsart="Herren", spielklasse="Kreisoberliga",
                        staffel="Kreisoberliga Mittelthüringen", sr_spesen=30.0, sra_spesen=25.0)
        # A TFV league match that was frozen with an earlier rate
        spiel_einfuegen(conn, uid, "tfv_alt_eingefroren", mannschaftsart="Herren",
                        spielklasse="Kreisoberliga", staffel="Kreisoberliga Mittelthüringen",
                        sr_spesen=28.0, sra_spesen=22.0)
        conn.close()
        migriere_bis(monkeypatch, 15)
        conn = _conn()
        try:
            return _saetze(conn)
        finally:
            conn.close()

    def test_fremder_verband_verliert_tfv_satz(self, leere_db, monkeypatch):
        saetze = self._seed(monkeypatch)
        assert saetze["altmark"] == (None, None)
        assert saetze["tfv_richtig"] == (30.0, 25.0)

    def test_tfv_punktspiel_bleibt_eingefroren(self, leere_db, monkeypatch):
        saetze = self._seed(monkeypatch)
        assert saetze["tfv_alt_eingefroren"] == (28.0, 22.0)


class TestMigration018Nofv:
    def test_nur_leere_nofv_pflichtspiele_werden_ergaenzt(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 17)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        spiel_einfuegen(conn, uid, "rl_leer", mannschaftsart="Herren",
                        spielklasse="Regionalliga Nordost", staffel="Regionalliga Nordost")
        spiel_einfuegen(conn, uid, "ol_leer", mannschaftsart="Herren",
                        spielklasse="Oberliga", staffel="NOFV-Oberliga Süd")
        spiel_einfuegen(conn, uid, "rl_von_hand", mannschaftsart="Herren",
                        spielklasse="Regionalliga Nordost", staffel="Regionalliga Nordost",
                        sr_spesen=1.0, sra_spesen=2.0)
        spiel_einfuegen(conn, uid, "aufstieg", mannschaftsart="C-Junioren",
                        spielklasse="Regionalliga Nordost", staffel="Aufstiegsspiel zur Regionalliga")
        spiel_einfuegen(conn, uid, "kreis_leer", mannschaftsart="Herren", spielklasse="Kreispokal")
        conn.close()

        migriere_bis(monkeypatch, 18)

        conn = _conn()
        try:
            saetze = _saetze(conn)
        finally:
            conn.close()
        assert saetze == {
            "rl_leer": (300.0, 150.0),
            "ol_leer": (100.0, 60.0),
            "rl_von_hand": (1.0, 2.0),
            "aufstieg": (None, None),
            "kreis_leer": (None, None),
        }


class TestMigration023DfbSpielId:
    def _bericht(self, conn, uid, spiel_id, datum, heim, gast, uhrzeit="14:00", kennung=""):
        conn.execute("""
            INSERT INTO spielberichte (user_id, dfb_spiel_id, saison, datum, uhrzeit, heim, gast,
                                       spielkennung, daten, scraped_at)
            VALUES (?, ?, '26/27', ?, ?, ?, ?, ?, '{}', '2026-11-01')
        """, (uid, spiel_id, datum, uhrzeit, heim, gast, kennung))
        conn.commit()

    def test_ids_und_kennungen_aus_den_berichten(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 22)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        fremd = nutzer_anlegen(conn, "kollege@example.org")
        anpfiff = "Sonntag · 27.09.2026 · 14:00 Uhr"
        # Different spelling in the duty roster: "II" instead of "U23"
        hertha = spiel_einfuegen(conn, uid, "hertha", datum="2026-09-27", anpfiff=anpfiff,
                                 heim_team="Hertha BSC U23", gast_team="FSV Zwickau")
        # Withdrawn: a different match was refereed on that day
        anderes = spiel_einfuegen(conn, uid, "anderes", datum="2026-09-27", anpfiff=anpfiff,
                                  heim_team="SV Musterdorf", gast_team="FC Beispiel")
        # Same match at the colleague's - their report is missing, so no ID
        kollege = spiel_einfuegen(conn, fremd, "hertha", datum="2026-09-27", anpfiff=anpfiff,
                                  heim_team="Hertha BSC U23", gast_team="FSV Zwickau")
        turnier = spiel_einfuegen(conn, uid, "turnier|Halle|x", datum="2026-09-27", anpfiff=anpfiff)
        self._bericht(conn, uid, "SPIEL1", "2026-09-27", "Hertha BSC II", "FSV Zwickau", kennung="690047011")
        self._bericht(conn, uid, "SPIEL2", "2026-09-28", "Hertha BSC II", "FSV Zwickau")
        conn.close()

        migriere_bis(monkeypatch, 23)

        conn = _conn()
        try:
            zeilen = {r["id"]: (r["dfb_spiel_id"], r["spielnummer"])
                      for r in conn.execute("SELECT id, dfb_spiel_id, spielnummer FROM matches")}
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("UPDATE matches SET dfb_spiel_id = 'SPIEL1' WHERE id = ?", (anderes,))
        finally:
            conn.close()
        assert zeilen[hertha] == ("SPIEL1", "690047011")
        assert zeilen[anderes] == (None, None)
        assert zeilen[kollege] == (None, None)
        assert zeilen[turnier] == (None, None)

    def test_mehrdeutig_bleibt_ohne_id(self, leere_db, monkeypatch):
        migriere_bis(monkeypatch, 22)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        for zeit in ("10:00", "12:00"):
            spiel_einfuegen(conn, uid, f"jugend-{zeit}", datum="2026-09-27",
                            anpfiff=f"Sonntag · 27.09.2026 · {zeit} Uhr",
                            heim_team="FC Heim", gast_team="SV Gast")
        # Report without kick-off: neither of the two can be sure
        self._bericht(conn, uid, "SPIEL1", "2026-09-27", "FC Heim", "SV Gast", uhrzeit="")
        # Unambiguous with kick-off
        self._bericht(conn, uid, "SPIEL2", "2026-09-27", "FC Heim", "SV Gast", uhrzeit="12:00")
        conn.close()

        migriere_bis(monkeypatch, 23)

        conn = _conn()
        try:
            ids = {r["match_key"]: r["dfb_spiel_id"] for r in conn.execute("SELECT * FROM matches")}
        finally:
            conn.close()
        assert ids == {"jugend-10:00": None, "jugend-12:00": "SPIEL2"}


class TestDatenUeberlebenDasUpdate:
    def test_spiel_von_version_drei_bis_heute(self, leere_db, tmp_path, monkeypatch):
        """A row from the earliest matches version arrives at the top undamaged."""
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "leer"))
        migriere_bis(monkeypatch, 3)
        conn = _conn()
        uid = nutzer_anlegen(conn)
        mid = spiel_einfuegen(conn, uid, "FC Heim|SV Gast|2025-11-08", heim_team="FC Heim",
                              gast_team="SV Gast", mannschaftsart="Herren", spielklasse="Kreisliga",
                              sr_spesen=25.0, sra_spesen=23.0)
        conn.execute("""
            INSERT INTO official_expenses (match_id, rolle, seq, km, oevm, updated_at)
            VALUES (?, 'SR', 0, 42, NULL, 'x')
        """, (mid,))
        conn.commit()
        conn.close()

        database.init_database()

        conn = _conn()
        try:
            zeile = conn.execute("SELECT * FROM matches WHERE id = ?", (mid,)).fetchone()
            km = conn.execute("SELECT km FROM official_expenses WHERE match_id = ?", (mid,)).fetchone()
        finally:
            conn.close()
        assert user_version() == _letzte_version()
        assert zeile["match_key"] == "FC Heim|SV Gast|2025-11-08|Herren|Kreisliga"
        assert (zeile["sr_spesen"], zeile["sra_spesen"]) == (25.0, 23.0)
        assert km["km"] == 42
