"""Stammdaten: verschluesselt gespeichert, im Klartext gelesen, leer heisst 'nichts geliefert'."""
import pytest
from cryptography.fernet import Fernet

import db.database as database
from db import stammdaten
from db.stammdaten import delete_stammdaten, get_stammdaten, upsert_stammdaten
from db_helpers import feste_uhr, nutzer_anlegen

DATEN = {
    "name_vorname": "Pfeife, Erika",
    "strasse": "Waldweg 1",
    "plz_ort": "99999 Irgendwo",
    "geburtsdatum": "01.02.1990",
    "email": "erika@example.org",
    "telefon_privat": "0361 123",
    "telefon_geschaeftlich": "0361 456",
    "telefon_mobil": "0170 789",
    "ausweisnummer": "SR-4711",
    "kreditor_nr": "K1",
    "debitor_nr": "D1",
    "bemerkung": "geheim",
    "verein": "FC Heim",
    "sr_gebiet": "Mittelthüringen",
    "schiedsrichter_seit": "01.08.2010",
    "qmax_sr": "Verbandsliga",
}


def _roh(user_id):
    conn = database.get_connection()
    try:
        return dict(conn.execute("SELECT * FROM stammdaten WHERE user_id = ?", (user_id,)).fetchone())
    finally:
        conn.close()


class TestRoundtrip:
    def test_vor_erstem_abruf_none(self, user):
        assert get_stammdaten(user["id"]) is None

    def test_klartext_zurueck(self, user):
        upsert_stammdaten(user["id"], DATEN)
        gelesen = get_stammdaten(user["id"])
        for feld, wert in DATEN.items():
            assert gelesen[feld] == wert, feld
        assert gelesen["foto_status"] == ""

    def test_persoenliche_felder_verschluesselt_in_der_datenbank(self, user):
        upsert_stammdaten(user["id"], DATEN)
        roh = _roh(user["id"])
        for feld in stammdaten._VERSCHLUESSELTE_FELDER:
            assert roh[feld] != DATEN[feld], feld
            assert DATEN[feld] not in roh[feld], feld

    def test_oeffentliche_felder_im_klartext(self, user):
        upsert_stammdaten(user["id"], DATEN)
        roh = _roh(user["id"])
        for feld in ("verein", "sr_gebiet", "schiedsrichter_seit", "qmax_sr"):
            assert roh[feld] == DATEN[feld], feld

    def test_werte_werden_getrimmt(self, user):
        upsert_stammdaten(user["id"], {"name_vorname": "  Pfeife, Erika ", "verein": " FC Heim "})
        gelesen = get_stammdaten(user["id"])
        assert gelesen["name_vorname"] == "Pfeife, Erika"
        assert gelesen["verein"] == "FC Heim"

    def test_unbekannte_schluessel_ignoriert(self, user):
        upsert_stammdaten(user["id"], {"verein": "FC Heim", "passwort": "nie speichern"})
        assert "passwort" not in get_stammdaten(user["id"])


class TestMerge:
    def test_leere_werte_lassen_bestand_stehen(self, user):
        upsert_stammdaten(user["id"], DATEN)
        upsert_stammdaten(user["id"], {"strasse": "", "verein": "", "telefon_mobil": None})
        gelesen = get_stammdaten(user["id"])
        assert gelesen["strasse"] == "Waldweg 1"
        assert gelesen["verein"] == "FC Heim"
        assert gelesen["telefon_mobil"] == "0170 789"

    def test_neue_werte_ueberschreiben(self, user):
        upsert_stammdaten(user["id"], DATEN)
        upsert_stammdaten(user["id"], {"strasse": "Neue Str. 2", "verein": "SV Neu"})
        gelesen = get_stammdaten(user["id"])
        assert gelesen["strasse"] == "Neue Str. 2"
        assert gelesen["verein"] == "SV Neu"
        assert gelesen["plz_ort"] == "99999 Irgendwo"

    def test_eine_zeile_je_nutzer(self, user):
        upsert_stammdaten(user["id"], DATEN)
        upsert_stammdaten(user["id"], DATEN)
        conn = database.get_connection()
        try:
            assert conn.execute("SELECT COUNT(*) FROM stammdaten").fetchone()[0] == 1
        finally:
            conn.close()

    def test_first_seen_bleibt(self, user):
        upsert_stammdaten(user["id"], DATEN, scraped_at="2026-01-01T00:00:00")
        upsert_stammdaten(user["id"], DATEN, scraped_at="2026-02-01T00:00:00")
        roh = _roh(user["id"])
        assert roh["first_seen_at"] == "2026-01-01T00:00:00"
        assert roh["scraped_at"] == "2026-02-01T00:00:00"

    def test_scraped_at_default_jetzt(self, user, monkeypatch):
        feste_uhr(monkeypatch, stammdaten)
        upsert_stammdaten(user["id"], DATEN)
        assert _roh(user["id"])["scraped_at"] == "2026-11-23T12:00:00+00:00"

    def test_fremde_verbindung_committet_nicht(self, user):
        conn = database.get_connection()
        try:
            upsert_stammdaten(user["id"], DATEN, conn=conn)
            conn.rollback()
        finally:
            conn.close()
        assert get_stammdaten(user["id"]) is None


class TestNutzertrennung:
    def test_jeder_sieht_nur_seine_daten(self, user):
        conn = database.get_connection()
        zweiter = nutzer_anlegen(conn, "kollege@example.org")
        conn.close()

        upsert_stammdaten(user["id"], DATEN)
        upsert_stammdaten(zweiter, {"name_vorname": "Fahne, Max"})
        assert get_stammdaten(user["id"])["name_vorname"] == "Pfeife, Erika"
        assert get_stammdaten(zweiter)["name_vorname"] == "Fahne, Max"
        assert get_stammdaten(zweiter)["strasse"] == ""


class TestSchluesselwechsel:
    def test_nicht_entschluesselbar_wird_leer(self, user, monkeypatch):
        upsert_stammdaten(user["id"], DATEN)
        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        gelesen = get_stammdaten(user["id"])
        assert gelesen["name_vorname"] == ""
        assert gelesen["strasse"] == ""
        # Unverschluesselte Felder bleiben lesbar
        assert gelesen["verein"] == "FC Heim"


class TestLoeschen:
    def test_loescht(self, user):
        upsert_stammdaten(user["id"], DATEN)
        assert delete_stammdaten(user["id"]) is True
        assert get_stammdaten(user["id"]) is None

    def test_nichts_da(self, user):
        assert delete_stammdaten(user["id"]) is False
