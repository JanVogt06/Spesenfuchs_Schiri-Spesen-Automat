"""
Ansetzungen aus der JSON-Schnittstelle der Schiriansetzung - ohne Browser.

Die Seite ist eine Attrappe: page.evaluate bekommt das Abruf-Skript samt
{url, methode, body} und antwortet aus einem Woerterbuch, so wie die
Schnittstelle am 24.11.2026 geantwortet hat (Daten erfunden).
"""
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from scraper import ansetzungen, sria_api
from scraper.ansetzungen import anpfiff_text, aufbereiten, hole_rohdaten, zeitraum

API = "https://api.dfbnet.org/api/referee/"


def person(rolle, vorname, nachname, **kw):
    daten = {"id": f"P{vorname}", "title": None, "firstName": vorname, "lastName": nachname,
             "phoneNumberMobile": None, "phoneNumberPrivate": None, "phoneNumberBusiness": None,
             "email": None, "street": None, "zipCode": None, "city": None,
             "countryIsoCode": "DE", "role": rolle, "appointmentConfirmed": True}
    daten.update(kw)
    return daten


ANSETZUNG = {
    "id": "SPIEL1", "kickoff": "2026-11-14T14:00:00+01:00", "divisionId": "STAFFEL1",
    "actionStates": [{"role": "REFEREE", "actionState": "APPOINTMENT_CONFIRMED"}],
    "referees": [
        person("ASSISTANT_2", "Paul", "Zwei", phoneNumberPrivate="0361 222"),
        person("OBSERVER", "Hans", "Pruefer"),
        person("REFEREE", "Max", "Muster", phoneNumberMobile="0151 111", phoneNumberPrivate="0361 999",
               email="max@example.org", street="Musterweg 1", zipCode="99999", city="Beispielstadt"),
        person("ASSISTANT_1", "Erika", "Eins", phoneNumberBusiness="0361 333"),
    ],
}

SPIEL = {
    "id": "SPIEL1", "homeTeamId": "TEAMH", "homeClubId": "CLUBH", "guestTeamId": "TEAMG",
    "guestClubId": "CLUBG", "goalsHome": None, "goalsGuest": None, "venueId": "PLATZ1",
    "kickoff": "2026-11-14T14:00:00+01:00", "matchDay": 12, "divisionId": "STAFFEL1",
    "divisionName": "coffeecom-Kreisoberliga", "divisionShortName": "00405101", "leagueId": 2067,
    "comment": None, "status": "REFEREE_PLANNED", "reasonForCancellation": None, "matchBlock": None,
}

ROHDATEN = {
    "ansetzungen": [ANSETZUNG],
    "spiele": {"SPIEL1": SPIEL},
    "teams": {"TEAMH": {"id": "TEAMH", "name": "SG FC Beispiel 2."},
              "TEAMG": {"id": "TEAMG", "name": "FSV Muster"}},
    "staetten": {"PLATZ1": {"id": "PLATZ1", "name": "Kunstrasen An der Aue", "type": "ARTIFICIAL_PITCH",
                            "address": {"street": "Auenweg", "zipCode": "07318", "city": "Saalfeld/Saale"}}},
    # Bewusst ein Pokal: die Spielklasse kommt aus dem Wettbewerb, nicht aus dem Team
    "wettbewerbe": {2067: {"id": "2067", "name": "Kreispokal", "leagueLevelName": "Kreispokal",
                           "teamTypeName": "Herren", "areaType": "COUNTY"}},
}


class TestAufbereiten:
    def test_struktur_wie_bisher_aus_den_modals(self):
        spiel = aufbereiten(ANSETZUNG, ROHDATEN)

        assert spiel["spiel_info"] == {
            "dfb_spiel_id": "SPIEL1",
            "anpfiff": "Samstag · 14.11.2026 · 14:00 Uhr",
            "heim_team": "SG FC Beispiel 2.",
            "gast_team": "FSV Muster",
            "mannschaftsart": "Herren",
            "spielklasse": "Kreispokal",
            "staffel": "coffeecom-Kreisoberliga",
            "spieltag": "12",
        }
        assert spiel["spielstaette"] == {
            "name": "Kunstrasen An der Aue",
            "adresse": "Auenweg, 07318 Saalfeld/Saale",
            "platz_typ": "Kunstrasenplatz",
            "lat": None,
            "lon": None,
        }

    def test_koordinaten_der_spielstaette(self):
        adresse = {"street": "Auenweg", "zipCode": "07318", "city": "Saalfeld/Saale",
                   "latitude": 50.6483, "longitude": "11.3659"}
        roh = {**ROHDATEN, "staetten": {"PLATZ1": {**ROHDATEN["staetten"]["PLATZ1"], "address": adresse}}}

        staette = aufbereiten(ANSETZUNG, roh)["spielstaette"]

        assert (staette["lat"], staette["lon"]) == (50.6483, 11.3659)

    @pytest.mark.parametrize("breite, laenge", [(0, 0), ("", None), ("kaputt", 11.0), (True, 11.0)])
    def test_unbrauchbare_koordinaten_gelten_als_fehlend(self, breite, laenge):
        adresse = {"zipCode": "07318", "city": "Saalfeld/Saale", "latitude": breite, "longitude": laenge}
        roh = {**ROHDATEN, "staetten": {"PLATZ1": {**ROHDATEN["staetten"]["PLATZ1"], "address": adresse}}}

        assert aufbereiten(ANSETZUNG, roh)["spielstaette"]["lat"] is None

    def test_markiert_die_eigene_person_ueber_die_schiri_id(self):
        gespann = aufbereiten(ANSETZUNG, {**ROHDATEN, "schiri_id": "PErika"})["schiedsrichter"]

        assert [(p["rolle"], p["selbst"]) for p in gespann] == [("SR", False), ("SRA 1", True), ("SRA 2", False)]

    def test_gespann_ohne_beobachter_in_formularreihenfolge(self):
        gespann = aufbereiten(ANSETZUNG, ROHDATEN)["schiedsrichter"]

        assert gespann == [
            {"rolle": "SR", "name": "Max Muster", "telefon": "0151 111", "email": "max@example.org",
             "strasse": "Musterweg 1", "plz_ort": "99999 Beispielstadt", "selbst": False},
            {"rolle": "SRA 1", "name": "Erika Eins", "telefon": "0361 333", "email": "",
             "strasse": "", "plz_ort": "", "selbst": False},
            {"rolle": "SRA 2", "name": "Paul Zwei", "telefon": "0361 222", "email": "",
             "strasse": "", "plz_ort": "", "selbst": False},
        ]

    def test_turnier_mit_mehreren_sr_ohne_teams(self):
        ansetzung = {**ANSETZUNG, "referees": [person("REFEREE", "A", "Eins"), person("REFEREE", "B", "Zwei")]}
        roh = {**ROHDATEN, "spiele": {"SPIEL1": {**SPIEL, "homeTeamId": None, "guestTeamId": None}}}

        spiel = aufbereiten(ansetzung, roh)

        assert spiel["spiel_info"]["heim_team"] == ""
        assert spiel["spiel_info"]["gast_team"] == ""
        assert [p["name"] for p in spiel["schiedsrichter"]] == ["A Eins", "B Zwei"]
        assert {p["rolle"] for p in spiel["schiedsrichter"]} == {"SR"}

    def test_unbekannte_platzart_bleibt_leer(self):
        roh = {**ROHDATEN, "staetten": {"PLATZ1": {"id": "PLATZ1", "name": "Halle", "type": "INDOOR",
                                                   "address": {"street": None, "zipCode": "99999",
                                                               "city": "Musterdorf"}}}}

        assert aufbereiten(ANSETZUNG, roh)["spielstaette"] == {
            "name": "Halle", "adresse": "99999 Musterdorf", "platz_typ": "", "lat": None, "lon": None}

    def test_spiel_fehlt(self):
        with pytest.raises(RuntimeError, match="nicht geliefert"):
            aufbereiten(ANSETZUNG, {**ROHDATEN, "spiele": {}})

    def test_ohne_spieltag(self):
        roh = {**ROHDATEN, "spiele": {"SPIEL1": {**SPIEL, "matchDay": None}}}
        assert aufbereiten(ANSETZUNG, roh)["spiel_info"]["spieltag"] == ""


class TestAnpfiff:
    @pytest.mark.parametrize("anstoss, text", [
        ("2026-11-14T14:00:00+01:00", "Samstag · 14.11.2026 · 14:00 Uhr"),
        ("2026-07-11T11:30:00+02:00", "Samstag · 11.07.2026 · 11:30 Uhr"),
        ("2026-09-16T19:00:00+02:00", "Mittwoch · 16.09.2026 · 19:00 Uhr"),
        (None, ""),
    ])
    def test_ortszeit_im_format_der_modals(self, anstoss, text):
        assert anpfiff_text(anstoss) == text


class TestZeitraum:
    def test_laufende_saison_bis_ein_jahr_voraus(self):
        assert zeitraum(date(2026, 11, 24)) == (date(2026, 6, 30), date(2027, 11, 24))

    def test_im_fruehjahr(self):
        assert zeitraum(date(2027, 3, 1)) == (date(2026, 6, 30), date(2028, 2, 29))

    def test_anfang_juli_noch_zwei_wochen_zurueck(self):
        assert zeitraum(date(2027, 7, 3)) == (date(2027, 6, 18), date(2028, 7, 2))


class Seite:
    """Antwortet auf das Abruf-Skript aus einer Tabelle Pfad -> Antwort."""

    def __init__(self, antworten=None, url="https://sria.dfbnet.org/referee/SCHIRI42/matches"):
        self.antworten = antworten or {}
        self.url = url
        self.abrufe = []
        self.pausen = []
        self.wait_function_aufrufe = []

    def evaluate(self, js, arg):
        assert js is sria_api._ABRUF_JS
        teile = urlparse(arg["url"])
        pfad = teile.path.removeprefix("/api/referee/")
        self.abrufe.append((arg["methode"], pfad, parse_qs(teile.query), arg["body"]))
        antwort = self.antworten[pfad]
        if callable(antwort):
            antwort = antwort(parse_qs(teile.query), arg["body"])
        return antwort

    def wait_for_timeout(self, ms):
        self.pausen.append(ms)

    def wait_for_function(self, js, timeout=None, polling=None):
        self.wait_function_aufrufe.append(js)


def ok(daten):
    return {"status": 200, "daten": daten}


class TestHoleRohdaten:
    def _seite(self):
        return Seite({
            "appointment/with-action-state": ok([ANSETZUNG]),
            "match": lambda q, b: ok([{**SPIEL, "id": i} for i in q["match-ids"]]),
            "club-team": lambda q, b: ok([{"id": i, "name": f"Team {i}"} for i in q["club-team-ids"]]),
            "venue/query": lambda q, b: ok([{"id": i, "name": "Platz"} for i in b["venueIds"]]),
            "league/2067": ok(ROHDATEN["wettbewerbe"][2067]),
        })

    def test_eine_handvoll_abrufe_fuer_alle_spiele(self):
        seite = self._seite()

        roh = hole_rohdaten(seite, "SCHIRI42", date(2026, 6, 30), date(2027, 11, 24))

        assert [(m, p) for m, p, _, _ in seite.abrufe] == [
            ("GET", "appointment/with-action-state"),
            ("GET", "match"),
            ("GET", "club-team"),
            ("POST", "venue/query"),
            ("GET", "league/2067"),
        ]
        _, _, query, _ = seite.abrufe[0]
        assert query["from"] == ["2026-06-30T00:00:00.000Z"]
        assert query["until"] == ["2027-11-24T00:00:00.000Z"]
        assert query["referee-id"] == ["SCHIRI42"]
        assert query["sort"] == ["kickoff,asc"]
        assert seite.abrufe[3][3] == {"venueIds": ["PLATZ1"]}
        assert set(roh["teams"]) == {"TEAMH", "TEAMG"}
        assert aufbereiten(ANSETZUNG, roh)["spiel_info"]["heim_team"] == "Team TEAMH"

    def test_blaettert_bis_zur_kurzen_seite(self, monkeypatch):
        monkeypatch.setattr(ansetzungen, "_SEITE", 2)
        seiten = {"0": [ANSETZUNG, ANSETZUNG], "1": [ANSETZUNG]}
        seite = self._seite()
        seite.antworten["appointment/with-action-state"] = lambda q, b: ok(seiten[q["page"][0]])

        roh = hole_rohdaten(seite, "SCHIRI42", date(2026, 6, 30), date(2027, 11, 24))

        assert len(roh["ansetzungen"]) == 3

    def test_ids_in_bloecken(self, monkeypatch):
        monkeypatch.setattr(sria_api, "BLOCK", 2)
        viele = [{**ANSETZUNG, "id": f"S{i}"} for i in range(5)]
        seite = self._seite()
        seite.antworten["appointment/with-action-state"] = ok(viele)

        hole_rohdaten(seite, "SCHIRI42", date(2026, 6, 30), date(2027, 11, 24))

        bloecke = [q["match-ids"] for m, p, q, _ in seite.abrufe if p == "match"]
        assert bloecke == [["S0", "S1"], ["S2", "S3"], ["S4"]]

    def test_ohne_ansetzungen(self):
        seite = Seite({"appointment/with-action-state": ok([])})

        roh = hole_rohdaten(seite, "SCHIRI42", date(2026, 6, 30), date(2027, 11, 24))

        assert roh["ansetzungen"] == []
        assert len(seite.abrufe) == 1
