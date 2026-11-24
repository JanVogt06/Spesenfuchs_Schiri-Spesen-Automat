"""Observations: replacing per (source, season), and when a season counts as fully read."""
from datetime import date

import pytest

import db.database as database
from db import beobachtungen as modul
from db.beobachtungen import (
    count_beobachtungen,
    delete_beobachtungen,
    get_beobachtungen,
    get_fertige_beobachtungs_saisons,
    replace_beobachtungs_saison,
)
from db_helpers import feste_uhr, nutzer_anlegen


def _b(datum="2025-09-20", uhrzeit="15:00", heim="FC Heim", gast="SV Gast", rolle="SR", note="8.4", **extra):
    return {"datum": datum, "uhrzeit": uhrzeit, "heim": heim, "gast": gast, "rolle": rolle,
            "note": note, "beobachter": "Herr Streng", "staffel": "Kreisoberliga", **extra}


@pytest.fixture
def zweiter(db):
    conn = database.get_connection()
    try:
        return nutzer_anlegen(conn, "kollege@example.org")
    finally:
        conn.close()


def _saison_zeile(uid, quelle, saison):
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM beobachtung_saisons WHERE user_id = ? AND quelle = ? AND saison = ?",
            (uid, quelle, saison),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


class TestReplace:
    def test_schreibt_und_zaehlt(self, user):
        n = replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(), _b(heim="Zwei")])
        assert n == 2
        assert count_beobachtungen(user["id"], "herren", "25/26") == 2
        assert _saison_zeile(user["id"], "herren", "25/26")["anzahl"] == 2

    def test_note_als_zahl(self, user):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(note="8.0")])
        assert get_beobachtungen(user["id"])["beobachtungen"][0]["note"] == 8.0

    def test_ersetzt_nur_dieselbe_quelle_und_saison(self, user):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(heim="Alt")])
        replace_beobachtungs_saison(user["id"], "portal", "25/26", [_b(heim="Portal")])
        replace_beobachtungs_saison(user["id"], "herren", "24/25", [_b(datum="2024-09-01")])
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(heim="Neu")])

        heims = {(b["quelle"], b["saison"], b["heim"]) for b in get_beobachtungen(user["id"])["beobachtungen"]}
        assert heims == {
            ("herren", "25/26", "Neu"), ("portal", "25/26", "Portal"), ("herren", "24/25", "FC Heim"),
        }

    def test_doppelte_zaehlen_einmal(self, user):
        assert replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(), _b()]) == 1
        assert _saison_zeile(user["id"], "herren", "25/26")["anzahl"] == 1

    def test_gleiches_spiel_zwei_rollen(self, user):
        assert replace_beobachtungs_saison(
            user["id"], "herren", "25/26", [_b(rolle="SR"), _b(rolle="SRA 1")]
        ) == 2

    def test_leere_saison_wird_vermerkt(self, user):
        assert replace_beobachtungs_saison(user["id"], "portal", "22/23", []) == 0
        assert _saison_zeile(user["id"], "portal", "22/23")["anzahl"] == 0

    def test_fehler_rollt_zurueck(self, user):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(heim="Bestand")])
        with pytest.raises(KeyError):
            replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(heim="Neu"), {"note": 1}])
        assert [b["heim"] for b in get_beobachtungen(user["id"])["beobachtungen"]] == ["Bestand"]

    def test_scraped_at_default_jetzt(self, user, monkeypatch):
        feste_uhr(monkeypatch, modul)
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b()])
        assert _saison_zeile(user["id"], "herren", "25/26")["scraped_at"] == "2026-11-23T12:00:00+00:00"


class TestFertigeSaisons:
    def _gelesen(self, uid, saison, am):
        replace_beobachtungs_saison(uid, "herren", saison, [], scraped_at=am)

    def test_ab_august_nach_saisonende_fertig(self, user):
        self._gelesen(user["id"], "24/25", "2025-08-01T00:00:00")
        assert get_fertige_beobachtungs_saisons(user["id"], "herren", date(2026, 11, 23)) == {"24/25"}

    def test_im_juli_gelesen_noch_nicht_fertig(self, user):
        self._gelesen(user["id"], "24/25", "2025-07-31T23:59:00")
        assert get_fertige_beobachtungs_saisons(user["id"], "herren", date(2026, 11, 23)) == set()

    def test_laufende_saison_nie_fertig(self, user):
        self._gelesen(user["id"], "26/27", "2026-11-20T00:00:00")
        assert get_fertige_beobachtungs_saisons(user["id"], "herren", date(2026, 11, 23)) == set()

    def test_quelle_getrennt(self, user):
        self._gelesen(user["id"], "24/25", "2025-09-01T00:00:00")
        assert get_fertige_beobachtungs_saisons(user["id"], "portal", date(2026, 11, 23)) == set()

    def test_unlesbare_werte_werden_uebersprungen(self, user):
        self._gelesen(user["id"], "kaputt", "2025-09-01T00:00:00")
        self._gelesen(user["id"], "23/24", "kein-datum")
        assert get_fertige_beobachtungs_saisons(user["id"], "herren", date(2026, 11, 23)) == set()

    def test_zwanzigstes_jahrhundert(self, user):
        self._gelesen(user["id"], "98/99", "2020-01-01T00:00:00")
        assert get_fertige_beobachtungs_saisons(user["id"], "herren", date(2026, 11, 23)) == {"98/99"}


class TestLesenUndLoeschen:
    def test_neueste_zuerst(self, user):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [
            _b(datum="2025-09-01", heim="A"), _b(datum="2025-10-01", heim="B"),
            _b(datum="2025-10-01", uhrzeit="18:00", heim="C"),
        ])
        daten = get_beobachtungen(user["id"])
        assert [b["heim"] for b in daten["beobachtungen"]] == ["C", "B", "A"]
        assert daten["saisons"][0]["anzahl"] == 3

    def test_nutzer_getrennt(self, user, zweiter):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b()])
        assert get_beobachtungen(zweiter) == {"saisons": [], "beobachtungen": []}
        assert count_beobachtungen(zweiter, "herren", "25/26") == 0

    def test_loeschen(self, user, zweiter):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [_b(), _b(heim="X")])
        replace_beobachtungs_saison(zweiter, "herren", "25/26", [_b()])
        assert delete_beobachtungen(user["id"]) == 2
        assert get_beobachtungen(user["id"]) == {"saisons": [], "beobachtungen": []}
        assert count_beobachtungen(zweiter, "herren", "25/26") == 1
