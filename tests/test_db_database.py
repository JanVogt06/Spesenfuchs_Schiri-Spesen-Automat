"""Nutzer, DFB-Zugangsdaten und die Protokolle fuer die Nutzungsstatistik."""
import sqlite3

import pytest

import db.database as database
from db.database import (
    count_downloads,
    create_user,
    get_all_users,
    get_dfb_credentials,
    get_user_by_email,
    get_user_by_id,
    log_download,
    log_login,
    log_spielbericht,
    update_dfb_credentials,
    update_user_password,
)
from db_helpers import feste_uhr


def _zeilen(tabelle):
    conn = database.get_connection()
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {tabelle} ORDER BY id")]
    finally:
        conn.close()


class TestVerbindung:
    def test_fremdschluessel_an(self, db):
        conn = database.get_connection()
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == database.BUSY_TIMEOUT_MS
        finally:
            conn.close()

    def test_zeilen_als_row(self, db):
        conn = database.get_connection()
        try:
            assert isinstance(conn.execute("SELECT 1 AS eins").fetchone(), sqlite3.Row)
        finally:
            conn.close()


class TestNutzer:
    def test_anlegen_und_finden(self, db, monkeypatch):
        feste_uhr(monkeypatch, database)
        uid = create_user("a@example.org", "hash-a")
        nach_mail = get_user_by_email("a@example.org")
        nach_id = get_user_by_id(uid)
        assert nach_mail == nach_id
        assert nach_mail["id"] == uid
        assert nach_mail["password_hash"] == "hash-a"
        assert nach_mail["created_at"] == "2026-11-23T12:00:00+00:00"
        assert nach_mail["dfb_username_encrypted"] is None

    def test_email_eindeutig(self, db):
        create_user("a@example.org", "x")
        with pytest.raises(sqlite3.IntegrityError):
            create_user("a@example.org", "y")

    def test_unbekannt(self, db):
        assert get_user_by_email("nie@example.org") is None
        assert get_user_by_id(999) is None

    def test_alle(self, db):
        assert get_all_users() == []
        a = create_user("a@example.org", "x")
        b = create_user("b@example.org", "y")
        assert sorted(u["id"] for u in get_all_users()) == [a, b]

    def test_passwort_aendern(self, user):
        assert update_user_password(user["id"], "neuer-hash") is True
        assert get_user_by_id(user["id"])["password_hash"] == "neuer-hash"

    def test_passwort_aendern_trifft_nur_einen(self, user):
        anderer = create_user("b@example.org", "alt")
        update_user_password(user["id"], "neu")
        assert get_user_by_id(anderer)["password_hash"] == "alt"


class TestDfbZugangsdaten:
    def test_ohne_daten_none(self, user):
        assert get_dfb_credentials(user["id"]) is None

    def test_speichern_und_lesen(self, user):
        update_dfb_credentials(user["id"], "enc-user", "enc-pass")
        assert get_dfb_credentials(user["id"]) == {
            "dfb_username_encrypted": "enc-user", "dfb_password_encrypted": "enc-pass",
        }

    def test_unvollstaendig_gilt_als_fehlend(self, user):
        update_dfb_credentials(user["id"], "enc-user", "")
        assert get_dfb_credentials(user["id"]) is None

    def test_unbekannter_nutzer(self, db):
        assert get_dfb_credentials(999) is None

    def test_nutzer_getrennt(self, user):
        anderer = create_user("b@example.org", "x")
        update_dfb_credentials(user["id"], "u", "p")
        assert get_dfb_credentials(anderer) is None


class TestProtokolle:
    def test_login(self, user, monkeypatch):
        feste_uhr(monkeypatch, database)
        log_login(user["id"])
        log_login(user["id"])
        zeilen = _zeilen("login_log")
        assert len(zeilen) == 2
        assert zeilen[0]["logged_in_at"] == "2026-11-23T12:00:00+00:00"

    def test_download_mit_spiel(self, user):
        log_download(user["id"], "Spesen_A_vs_B.docx", "docx", match_id=7)
        [zeile] = _zeilen("download_log")
        assert (zeile["match_id"], zeile["session_id"], zeile["file_type"]) == (7, None, "docx")

    def test_download_altlast_session(self, user):
        log_download(user["id"], "alt.pdf", "pdf", session_id="session_x")
        assert _zeilen("download_log")[0]["session_id"] == "session_x"

    def test_count_downloads(self, user):
        assert count_downloads() == 0
        anderer = create_user("b@example.org", "x")
        log_download(user["id"], "a.docx", "docx", match_id=1)
        log_download(anderer, "b.docx", "docx", match_id=1)
        log_download(user["id"], "c.zip", "zip")
        assert count_downloads() == 3


class TestSpielberichtLog:
    @pytest.fixture
    def uhr(self, monkeypatch):
        return feste_uhr(monkeypatch, database)

    def test_eintrag(self, user, uhr):
        log_spielbericht(user["id"], 5, "ansehen", "saison")
        [zeile] = _zeilen("spielbericht_log")
        assert (zeile["spielbericht_id"], zeile["aktion"], zeile["quelle"], zeile["dokument_id"]) == \
            (5, "ansehen", "saison", None)
        assert zeile["geklickt_am"] == "2026-11-23T12:00:00+00:00"

    def test_quelle_default_direkt(self, user, uhr):
        log_spielbericht(user["id"], 5, "ansehen")
        assert _zeilen("spielbericht_log")[0]["quelle"] == "direkt"

    def test_doppelklick_zaehlt_einmal(self, user, uhr):
        log_spielbericht(user["id"], 5, "ansehen", "spesen")
        uhr.weiter(seconds=9)
        log_spielbericht(user["id"], 5, "ansehen", "spesen")
        assert len(_zeilen("spielbericht_log")) == 1

    def test_genau_zehn_sekunden_noch_doppelt(self, user, uhr):
        log_spielbericht(user["id"], 5, "ansehen", "spesen")
        uhr.weiter(seconds=10)
        log_spielbericht(user["id"], 5, "ansehen", "spesen")
        assert len(_zeilen("spielbericht_log")) == 1

    def test_nach_elf_sekunden_neuer_eintrag(self, user, uhr):
        log_spielbericht(user["id"], 5, "ansehen", "spesen")
        uhr.weiter(seconds=11)
        log_spielbericht(user["id"], 5, "ansehen", "spesen")
        assert len(_zeilen("spielbericht_log")) == 2

    def test_sperrfenster_laeuft_ab_dem_gezaehlten_eintrag(self, user, uhr):
        """Ein verworfener Klick verlaengert das Fenster nicht."""
        log_spielbericht(user["id"], 5, "ansehen")
        uhr.weiter(seconds=8)
        log_spielbericht(user["id"], 5, "ansehen")
        uhr.weiter(seconds=8)
        log_spielbericht(user["id"], 5, "ansehen")
        assert len(_zeilen("spielbericht_log")) == 2

    @pytest.mark.parametrize("anders", [
        {"spielbericht_id": 6},
        {"aktion": "dokument_laden"},
        {"quelle": "saison"},
        {"dokument_id": 3},
    ])
    def test_anderer_eintrag_zaehlt_sofort(self, user, uhr, anders):
        basis = {"spielbericht_id": 5, "aktion": "ansehen", "quelle": "spesen", "dokument_id": None}
        log_spielbericht(user["id"], **basis)
        log_spielbericht(user["id"], **{**basis, **anders})
        assert len(_zeilen("spielbericht_log")) == 2

    def test_anderer_nutzer_zaehlt_sofort(self, user, uhr):
        anderer = create_user("b@example.org", "x")
        log_spielbericht(user["id"], 5, "ansehen")
        log_spielbericht(anderer, 5, "ansehen")
        assert len(_zeilen("spielbericht_log")) == 2

    def test_dokumente_desselben_berichts_getrennt(self, user, uhr):
        log_spielbericht(user["id"], 5, "dokument_oeffnen", "bericht", dokument_id=1)
        log_spielbericht(user["id"], 5, "dokument_oeffnen", "bericht", dokument_id=2)
        log_spielbericht(user["id"], 5, "dokument_oeffnen", "bericht", dokument_id=1)
        assert [z["dokument_id"] for z in _zeilen("spielbericht_log")] == [1, 2]
