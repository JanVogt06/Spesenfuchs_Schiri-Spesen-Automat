"""
Season summary from the interface - without a browser (data invented).

The expected values have the form the old table reading wrote to the
database ("-" for empty, "2 : 0", "Beo." in the crew).
"""
from datetime import date, datetime, timezone

import pytest

from main import persist_saisons
from db.season import get_saison
from scraper import saisons
from scraper.saisons import angebotene_saisons, bilanz, lies_saisons, saison_zeitraum, spielzeile
from test_scraper_ansetzungen import Seite, ok

JETZT = datetime(2026, 11, 24, 13, 10, 30, 865000, tzinfo=timezone.utc)

SAISONS = [
    {"name": "27/28", "start": "2027-07-01", "end": "2028-06-30"},
    {"name": "26/27", "start": "2026-07-01", "end": "2027-06-30"},
    {"name": "25/26", "start": "2025-07-01", "end": "2026-06-30"},
    {"name": "18/19", "start": "2018-07-01", "end": "2019-06-30"},
    {"name": "17/18", "start": "2017-07-01", "end": "2018-06-30"},
]


def person(rolle, vorname, nachname, pid="X"):
    return {"id": pid, "role": rolle, "firstName": vorname, "lastName": nachname, "email": "x@example.org"}


SPIEL = {
    "id": "SPIEL1", "kickoff": "2026-11-22T13:30:00+01:00",
    "league": {"id": "70", "name": "Regionalliga Nordost"}, "divisionShortName": "RLNO1",
    "goalsHome": 2, "goalsGuest": 0,
    "yellowCardsHome": 1, "yellowRedCardsHome": 0, "redCardsHome": 0,
    "yellowCardsGuest": 3, "yellowRedCardsGuest": 0, "redCardsGuest": 0,
    "referees": [
        person("ASSISTANT_1", "Paul", "Fahne"),
        person("OBSERVER", "Bodo", "Pruefer"),
        person("REFEREE", "Max", "Pfeife"),
        person("ASSISTANT_2", "Erika", "Selbst", pid="SCHIRI42"),
    ],
}

SUMME = {
    "referee": {"officiated": 26, "returned": 1, "notAppeared": None},
    "assistant1": {"officiated": 8, "returned": None, "notAppeared": None},
    "assistant2": {"officiated": 4, "returned": None, "notAppeared": None},
    "observer": {"officiated": 1, "returned": None, "notAppeared": None},
    "fourthOfficial": {"officiated": None, "returned": None, "notAppeared": None},
}
BEFREIUNG = {"trainingCoursesCreditable": 1, "trainingCoursesOnlineCreditable": 0,
             "performanceTests": 0, "otherEffortsCreditable": 0}


class TestSpielzeile:
    def test_form_der_alten_tabelle(self):
        zeile = spielzeile(
            SPIEL,
            {"SPIEL1": {"id": "SPIEL1", "homeTeamId": "H", "guestTeamId": "G"}},
            {"H": {"name": "BFC Preussen"}, "G": {"name": "BSG Chemie Leipzig"}},
            "SCHIRI42",
        )

        assert zeile == {
            "datum_text": "22.11.26, 13:30",
            "liga": "Regionalliga Nordost",
            "heim": "BFC Preussen",
            "gast": "BSG Chemie Leipzig",
            "ergebnis": "2 : 0",
            "heim_gelb": 1, "heim_gelbrot": 0, "heim_rot": 0,
            "gast_gelb": 3, "gast_gelbrot": 0, "gast_rot": 0,
            "gespann": [
                {"rolle": "SR", "name": "Max Pfeife", "selbst": False},
                {"rolle": "SRA 1", "name": "Paul Fahne", "selbst": False},
                {"rolle": "SRA 2", "name": "Erika Selbst", "selbst": True},
                {"rolle": "Beo.", "name": "Bodo Pruefer", "selbst": False},
            ],
        }

    def test_turnier_ohne_ergebnis_und_teams(self):
        spiel = {**SPIEL, "goalsHome": None, "goalsGuest": None,
                 "referees": [person("REFEREE", "A", "Eins", pid="SCHIRI42"), person("REFEREE", "B", "Zwei"),
                              person("MENTOR", "P", "Pate")]}
        details = {"SPIEL1": {"id": "SPIEL1", "homeTeamId": None, "guestTeamId": None,
                              "matchBlock": {"blockName": "NOFV U 16-Junioren Regionalturnier 2026, 3. Tag, NR 1"}}}

        zeile = spielzeile(spiel, details, {}, "SCHIRI42")

        assert (zeile["ergebnis"], zeile["heim"], zeile["gast"]) == \
            ("- : -", "NOFV U 16-Junioren Regionalturnier 2026, 3. Tag, NR 1", "")
        assert [(p["rolle"], p["selbst"]) for p in zeile["gespann"]] == [
            ("SR", True), ("SR", False), ("Pate", False)]

    def test_halbes_ergebnis(self):
        assert spielzeile({**SPIEL, "goalsGuest": None}, {}, {}, "X")["ergebnis"] == "2 : -"


class TestBilanz:
    def test_zeilen_wie_auf_der_karte(self):
        einsaetze, lehrgaenge = bilanz(SUMME, BEFREIUNG)

        assert [(z["rolle"], z["geleitet"], z["zurueckgegeben"], z["nicht_angetreten"]) for z in einsaetze] == [
            ("SR", "26", "1", "-"),
            ("SRA 1", "8", "-", "-"),
            ("SRA 2", "4", "-", "-"),
            ("4. Off.", "-", "-", "-"),
            ("Beo", "1", "-", "-"),
            ("VA", "-", "-", "-"),
            ("AVA", "-", "-", "-"),
            ("VAC", "-", "-", "-"),
            ("Coach", "-", "-", "-"),
            ("Pate", "-", "-", "-"),
            ("Sonstiger Einsatz", "-", "", ""),
            ("Summe", "39", "1", "-"),
        ]
        assert lehrgaenge == {"lehrabend": "1", "lehrabend_online": "-", "leistungspruefung": "-"}

    def test_sonstiger_einsatz_zaehlt_zur_summe(self):
        einsaetze, _ = bilanz({"referee": {"officiated": 2}}, {"otherEffortsCreditable": 3})
        assert einsaetze[-2]["geleitet"] == "3"
        assert einsaetze[-1]["geleitet"] == "5"

    def test_leer(self):
        einsaetze, lehrgaenge = bilanz(None, None)
        assert einsaetze[-1] == {"rolle": "Summe", "geleitet": "-", "zurueckgegeben": "-",
                                 "nicht_angetreten": "-"}
        assert set(lehrgaenge.values()) == {"-"}


class TestZeitraum:
    def test_laufende_saison_nur_bis_jetzt(self):
        assert saison_zeitraum(SAISONS[1], JETZT) == (
            "2026-07-01T00:00:00.000Z", "2026-11-24T13:10:30.865Z")

    def test_abgeschlossene_saison_bis_zum_ende(self):
        assert saison_zeitraum(SAISONS[2], JETZT) == (
            "2025-07-01T00:00:00.000Z", "2026-06-30T21:59:59.999Z")

    def test_ab_schiedsrichter_seit_ohne_zukunft(self):
        namen = [s["name"] for s in angebotene_saisons(SAISONS, "2019-01-26", date(2026, 11, 24))]
        assert namen == ["26/27", "25/26", "18/19"]

    def test_ohne_seit_alle_bisherigen(self):
        namen = [s["name"] for s in angebotene_saisons(SAISONS, None, date(2026, 11, 24))]
        assert namen == ["26/27", "25/26", "18/19", "17/18"]


def schnittstelle(spiele_je_saison, fehler_bei=()):
    def spiele(q, b):
        saison = next(s["name"] for s in SAISONS if q["from"][0].startswith(s["start"]))
        if saison in fehler_bei:
            return {"status": 500}
        return ok(spiele_je_saison.get(saison, []))

    return Seite({
        "referee/SCHIRI42": ok({"refereeSince": "2025-08-01"}),
        "season": ok(SAISONS),
        "appointment/with-match-details": spiele,
        "match": lambda q, b: ok([{"id": i, "homeTeamId": "H", "guestTeamId": "G"} for i in q["match-ids"]]),
        "club-team": lambda q, b: ok([{"id": i, "name": f"Team {i}"} for i in q["club-team-ids"]]),
        "appointment/summary": ok(SUMME),
        "referee/SCHIRI42/exemption/summary": ok(BEFREIUNG),
    }, url="https://sria.dfbnet.org/referee/SCHIRI42/matches")


class TestLiesSaisons:
    def test_liest_alle_ausser_fertigen_aber_nie_die_laufende(self):
        seite = schnittstelle({"26/27": [SPIEL], "25/26": [SPIEL, {**SPIEL, "id": "SPIEL2"}]})
        fortschritt = []

        ergebnis = lies_saisons(seite, "SCHIRI42", ueberspringen={"26/27", "25/26"},
                                progress_callback=lambda *a: fortschritt.append(a), jetzt=JETZT)

        assert list(ergebnis) == ["26/27"]
        assert fortschritt == [(1, 1, "Saison 26/27 (1/1)")]
        saison = ergebnis["26/27"]
        assert saison["vollstaendig"] is True
        assert saison["erwartet"] == 1
        assert saison["spiele"][0]["heim"] == "Team H"
        assert saison["lehrgaenge"]["lehrabend"] == "1"

    def test_fehler_in_einer_saison(self):
        seite = schnittstelle({"26/27": [SPIEL]}, fehler_bei={"25/26"})
        ergebnis = lies_saisons(seite, "SCHIRI42", jetzt=JETZT)
        assert list(ergebnis) == ["26/27"]

    def test_leere_tabelle_aber_bilanz_kennt_spiele(self):
        ergebnis = lies_saisons(schnittstelle({}), "SCHIRI42", jetzt=JETZT)
        assert ergebnis["26/27"]["vollstaendig"] is False

    def test_wirklich_leere_saison(self):
        seite = schnittstelle({})
        seite.antworten["appointment/summary"] = ok({})
        ergebnis = lies_saisons(seite, "SCHIRI42", jetzt=JETZT)
        assert ergebnis["26/27"]["vollstaendig"] is True
        assert ergebnis["26/27"]["spiele"] == []

    def test_abgelaufene_sitzung_behaelt_das_gelesene(self):
        seite = schnittstelle({"26/27": [SPIEL]})
        antworten = iter([ok(SUMME), {"status": 401}, {"status": 401}])
        seite.antworten["appointment/summary"] = lambda q, b: next(antworten)

        ergebnis = lies_saisons(seite, "SCHIRI42", jetzt=JETZT)

        assert list(ergebnis) == ["26/27"]

    def test_seiten_mit_langsamen_spielen_werden_geteilt(self):
        # As on 24.11.2026: two slow matches on one page -> 500
        alle = [{**SPIEL, "id": f"S{i:02d}"} for i in range(45)]
        langsam = {25, 27}
        abrufe = []

        def server(q, b):
            groesse, seite = int(q["size"][0]), int(q["page"][0])
            bereich = range(groesse * seite, groesse * (seite + 1))
            abrufe.append((groesse, seite))
            if not q["from"][0].startswith("2026"):
                return ok([])
            if len(langsam & set(bereich)) >= 2:
                return {"status": 500}
            return ok([alle[i] for i in bereich if i < len(alle)])

        seite = schnittstelle({})
        seite.antworten["appointment/with-match-details"] = server

        ergebnis = lies_saisons(seite, "SCHIRI42", jetzt=JETZT)

        assert [z["datum_text"] for z in ergebnis["26/27"]["spiele"]] == ["22.11.26, 13:30"] * 45
        assert ergebnis["26/27"]["erwartet"] == 45
        # Every failing page gets a second attempt (the server
        # caches), only then is it split. The first retrievals belong to 26/27.
        assert abrufe[:15] == [(20, 0), (20, 1), (20, 1), (10, 2), (10, 2), (5, 4), (5, 5), (5, 5),
                               (1, 25), (1, 26), (1, 27), (1, 28), (1, 29), (10, 3), (20, 2)]
        assert seite.pausen == [3000, 3000, 3000]

    def test_blaettert(self, monkeypatch):
        monkeypatch.setattr(saisons, "_SEITE", 1)
        seiten = {"0": [SPIEL], "1": [{**SPIEL, "id": "SPIEL2"}], "2": []}
        seite = schnittstelle({})
        seite.antworten["appointment/with-match-details"] = lambda q, b: ok(
            seiten[q["page"][0]] if q["from"][0].startswith("2026") else [])

        ergebnis = lies_saisons(seite, "SCHIRI42", jetzt=JETZT)

        assert ergebnis["26/27"]["erwartet"] == 2


class TestBisInDieDatenbank:
    def test_persist_saisons_versteht_das_ergebnis(self, user):
        ergebnis = lies_saisons(schnittstelle({"26/27": [SPIEL]}), "SCHIRI42", jetzt=JETZT)

        # 25/26 is empty in the test, but not according to the summary - it is left out
        assert ergebnis["25/26"]["vollstaendig"] is False
        assert persist_saisons(user["id"], ergebnis) == 1

        saison = get_saison(user["id"], "26/27")
        spiel, = saison["spiele"]
        assert (spiel["datum"], spiel["uhrzeit"], spiel["ergebnis"], spiel["eigene_rolle"]) == \
            ("2026-11-22", "13:30", "2 : 0", "SRA 2")
        assert spiel["heim_gelb"] == 1
        # get_saison sorts the crew by role
        assert [(p["rolle"], p["ist_selbst"]) for p in spiel["gespann"]] == [
            ("Beo.", False), ("SR", False), ("SRA 1", False), ("SRA 2", True)]
