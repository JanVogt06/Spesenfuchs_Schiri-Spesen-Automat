"""Geleitete Spiele und Saisonbilanz: saisonweise ersetzend, in einer Transaktion."""
import pytest

import db.database as database
from db import season
from db.season import (
    build_saison_match_key,
    count_saison_spiele,
    delete_saisons,
    get_komplette_saisons,
    get_saison,
    get_saisons,
    replace_saison,
)
from db_helpers import feste_uhr, nutzer_anlegen


@pytest.fixture
def zweiter(db):
    conn = database.get_connection()
    try:
        return nutzer_anlegen(conn, "kollege@example.org")
    finally:
        conn.close()


def _spiel(datum="2025-09-20", uhrzeit="15:00", heim="FC Heim", gast="SV Gast", **extra):
    return {
        "datum": datum, "uhrzeit": uhrzeit, "liga": "Kreisoberliga", "heim": heim, "gast": gast,
        "ergebnis": "2:1", "heim_gelb": "3", "heim_gelbrot": "-", "heim_rot": "0",
        "gast_gelb": 1, "gast_gelbrot": None, "gast_rot": "",
        "eigene_rolle": "SR",
        "gespann": [
            {"rolle": "SR", "name": " Ich ", "selbst": True},
            {"rolle": "SRA", "name": "Erster"},
            {"rolle": "SRA", "name": "Zweiter"},
        ],
        **extra,
    }


EINSAETZE = [
    {"rolle": "SR", "geleitet": " 12 ", "zurueckgegeben": "1", "nicht_angetreten": "0"},
    {"rolle": "SRA", "geleitet": "4", "zurueckgegeben": "", "nicht_angetreten": None},
    {"rolle": "", "geleitet": "99"},
]
LEHRGAENGE = {"lehrabend": " 5 ", "lehrabend_online": "2", "leistungspruefung": "bestanden"}


def _replace(uid, saison="25/26", spiele=None, einsaetze=None, lehrgaenge=None, **kw):
    return replace_saison(
        uid, saison,
        spiele if spiele is not None else [_spiel()],
        einsaetze if einsaetze is not None else EINSAETZE,
        lehrgaenge if lehrgaenge is not None else LEHRGAENGE,
        **kw,
    )


class TestSchluessel:
    def test_mit_uhrzeit(self):
        assert build_saison_match_key("2025-09-20", " FC Heim", "SV Gast ", "15:00") == \
            "2025-09-20|15:00|FC Heim|SV Gast"

    def test_none_teams(self):
        assert build_saison_match_key("2025-09-20", None, None, "") == "2025-09-20|||"


class TestReplaceSaison:
    def test_schreibt_spiele_gespann_einsaetze_lehrgaenge(self, user):
        assert _replace(user["id"]) == 1
        s = get_saison(user["id"], "25/26")

        spiel = s["spiele"][0]
        assert spiel["match_key"] == "2025-09-20|15:00|FC Heim|SV Gast"
        assert (spiel["heim_gelb"], spiel["heim_gelbrot"], spiel["heim_rot"]) == (3, None, 0)
        assert (spiel["gast_gelb"], spiel["gast_gelbrot"], spiel["gast_rot"]) == (1, None, None)
        assert spiel["gespann"] == [
            {"rolle": "SR", "name": "Ich", "ist_selbst": True},
            {"rolle": "SRA", "name": "Erster", "ist_selbst": False},
            {"rolle": "SRA", "name": "Zweiter", "ist_selbst": False},
        ]
        assert s["einsaetze"] == [
            {"rolle": "SR", "geleitet": "12", "zurueckgegeben": "1", "nicht_angetreten": "0"},
            {"rolle": "SRA", "geleitet": "4", "zurueckgegeben": "", "nicht_angetreten": ""},
        ]
        assert s["lehrgaenge"]["lehrabend"] == "5"
        assert s["lehrgaenge"]["leistungspruefung"] == "bestanden"

    def test_ersetzt_die_saison_vollstaendig(self, user):
        _replace(user["id"], spiele=[_spiel(heim="Alt"), _spiel(heim="Alt2")])
        _replace(user["id"], spiele=[_spiel(heim="Neu")], einsaetze=[{"rolle": "SR", "geleitet": "1"}])
        s = get_saison(user["id"], "25/26")
        assert [sp["heim"] for sp in s["spiele"]] == ["Neu"]
        assert [e["rolle"] for e in s["einsaetze"]] == ["SR"]

        conn = database.get_connection()
        try:
            # Keine verwaisten Gespann-Zeilen der alten Spiele
            assert conn.execute("SELECT COUNT(*) FROM season_match_officials").fetchone()[0] == 3
        finally:
            conn.close()

    def test_andere_saisons_und_nutzer_bleiben(self, user, zweiter):
        _replace(user["id"], "24/25", spiele=[_spiel(datum="2024-09-01")])
        _replace(zweiter, "25/26")
        _replace(user["id"], "25/26", spiele=[_spiel(heim="Neu")])
        _replace(user["id"], "25/26", spiele=[_spiel(heim="Neuer")])

        assert count_saison_spiele(user["id"], "24/25") == 1
        assert count_saison_spiele(zweiter, "25/26") == 1
        assert get_saison(zweiter, "25/26")["spiele"][0]["heim"] == "FC Heim"

    def test_doppeltes_spiel_wird_uebersprungen(self, user):
        assert _replace(user["id"], spiele=[_spiel(), _spiel()]) == 1
        assert count_saison_spiele(user["id"], "25/26") == 1

    def test_ohne_datum_platzhalter(self, user):
        _replace(user["id"], spiele=[_spiel(datum="")])
        assert get_saison(user["id"], "25/26")["spiele"][0]["datum"] == "1900-01-01"

    def test_rolle_im_gespann_default_sr(self, user):
        _replace(user["id"], spiele=[_spiel(gespann=[{"rolle": "", "name": "X"}, {"name": "Y"}])])
        assert [p["rolle"] for p in get_saison(user["id"], "25/26")["spiele"][0]["gespann"]] == ["SR", "SR"]

    def test_erwartet_default_anzahl_spiele(self, user):
        _replace(user["id"], spiele=[_spiel(heim="A"), _spiel(heim="B")])
        assert get_komplette_saisons(user["id"]) == {"25/26"}

    def test_scraped_at_default_jetzt(self, user, monkeypatch):
        feste_uhr(monkeypatch, season)
        _replace(user["id"])
        assert get_saison(user["id"], "25/26")["lehrgaenge"]["scraped_at"] == "2026-11-23T12:00:00+00:00"

    def test_fehler_rollt_zurueck(self, user):
        _replace(user["id"], spiele=[_spiel(heim="Bestand")])
        with pytest.raises(AttributeError):
            _replace(user["id"], spiele=[_spiel(heim="Neu"), "kaputt"])
        s = get_saison(user["id"], "25/26")
        assert [sp["heim"] for sp in s["spiele"]] == ["Bestand"]
        assert len(s["einsaetze"]) == 2


class TestKompletteSaisons:
    def test_vollstaendig(self, user):
        _replace(user["id"], erwartet=1)
        assert get_komplette_saisons(user["id"]) == {"25/26"}

    def test_als_unvollstaendig_gemeldet(self, user):
        _replace(user["id"], vollstaendig=False)
        assert get_komplette_saisons(user["id"]) == set()

    def test_trefferzahl_weicht_ab(self, user):
        _replace(user["id"], erwartet=5)
        assert get_komplette_saisons(user["id"]) == set()

    def test_ohne_einsatzbilanz(self, user):
        _replace(user["id"], einsaetze=[])
        assert get_komplette_saisons(user["id"]) == set()

    def test_leere_saison_mit_bilanz_ist_komplett(self, user):
        _replace(user["id"], spiele=[], erwartet=0)
        assert get_komplette_saisons(user["id"]) == {"25/26"}

    def test_nutzer_getrennt(self, user, zweiter):
        _replace(user["id"])
        assert get_komplette_saisons(zweiter) == set()


class TestLesen:
    def test_get_saisons_neueste_zuerst_mit_zahlen(self, user):
        _replace(user["id"], "23/24", spiele=[_spiel(datum="2023-10-01")])
        _replace(user["id"], "25/26", spiele=[_spiel(datum="2025-09-01"), _spiel(datum="2025-10-01")],
                 scraped_at="2026-01-01T00:00:00")
        _replace(user["id"], "24/25", spiele=[_spiel(datum="2024-10-01")])
        saisons = get_saisons(user["id"])
        assert [s["saison"] for s in saisons] == ["25/26", "24/25", "23/24"]
        assert saisons[0]["spiele"] == 2
        assert saisons[0]["letztes_spiel"] == "2025-10-01"
        assert saisons[0]["scraped_at"] == "2026-01-01T00:00:00"

    def test_saison_nur_mit_lehrgaengen_erscheint(self, user):
        _replace(user["id"], "26/27", spiele=[], einsaetze=[])
        saisons = get_saisons(user["id"])
        assert [(s["saison"], s["spiele"], s["letztes_spiel"]) for s in saisons] == [("26/27", 0, None)]

        s = get_saison(user["id"], "26/27")
        assert s["spiele"] == []
        assert s["lehrgaenge"] is not None

    def test_unbekannte_saison(self, user):
        assert get_saison(user["id"], "19/20") is None
        assert get_saisons(user["id"]) == []

    def test_spiele_nach_datum_und_zeit(self, user):
        _replace(user["id"], spiele=[
            _spiel(datum="2025-09-20", uhrzeit="10:00", heim="Frueh"),
            _spiel(datum="2025-09-20", uhrzeit="15:00", heim="Spaet"),
            _spiel(datum="2025-10-01", uhrzeit="12:00", heim="Oktober"),
        ])
        assert [s["heim"] for s in get_saison(user["id"], "25/26")["spiele"]] == ["Oktober", "Spaet", "Frueh"]

    def test_fremde_saison_unsichtbar(self, user, zweiter):
        _replace(zweiter)
        assert get_saison(user["id"], "25/26") is None


class TestLoeschen:
    def test_loescht_alles_des_nutzers(self, user, zweiter):
        _replace(user["id"], "24/25", spiele=[_spiel(heim="A"), _spiel(heim="B")])
        _replace(user["id"], "25/26")
        _replace(zweiter, "25/26")

        assert delete_saisons(user["id"]) == 3
        assert get_saisons(user["id"]) == []
        assert get_saison(zweiter, "25/26") is not None

        conn = database.get_connection()
        try:
            for tabelle in ("season_appearances", "season_education"):
                n = conn.execute(f"SELECT COUNT(*) FROM {tabelle} WHERE user_id = ?", (user["id"],)).fetchone()[0]
                assert n == 0, tabelle
            assert conn.execute("SELECT COUNT(*) FROM season_match_officials").fetchone()[0] == 3
        finally:
            conn.close()

    def test_nichts_zu_loeschen(self, user):
        assert delete_saisons(user["id"]) == 0
