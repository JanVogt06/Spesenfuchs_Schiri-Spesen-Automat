"""
Der Zugriff auf die Schnittstelle der Ansetzungs-App - ohne Browser.
"""
from datetime import date

import pytest

from scraper import ansetzungen, sria_api
from scraper.sria_api import SitzungAbgelaufen, datum_de, warte_auf_app
from test_scraper_ansetzungen import Seite, ok


class TestAbruf:
    def test_token_wird_einmal_abgewartet(self):
        antworten = iter([{"status": 401}, ok([])])
        seite = Seite({"appointment/with-action-state": lambda q, b: next(antworten)})

        assert ansetzungen.hole_ansetzungen(seite, "S", date(2026, 7, 1), date(2027, 7, 1)) == []
        assert seite.pausen == [2000]

    def test_dauerhaft_abgelehnt(self):
        seite = Seite({"appointment/with-action-state": {"status": 401}})
        with pytest.raises(SitzungAbgelaufen):
            ansetzungen.hole_ansetzungen(seite, "S", date(2026, 7, 1), date(2027, 7, 1))

    def test_serverfehler_einmal_wiederholt(self):
        antworten = iter([{"status": 503}, ok([])])
        seite = Seite({"appointment/with-action-state": lambda q, b: next(antworten)})

        assert ansetzungen.hole_ansetzungen(seite, "S", date(2026, 7, 1), date(2027, 7, 1)) == []
        assert seite.pausen == [3000]

    def test_keine_antwort_gilt_als_serverfehler(self):
        seite = Seite({"season": {"status": 0}})
        with pytest.raises(sria_api.Serverfehler, match="HTTP 0"):
            sria_api.abruf(seite, "GET", "season")
        assert seite.pausen == [3000]

    def test_serverfehler_ohne_wiederholung(self):
        seite = Seite({"season": {"status": 500}})
        with pytest.raises(sria_api.Serverfehler):
            sria_api.abruf(seite, "GET", "season", wiederholen=False)
        assert seite.pausen == []

    def test_serverfehler(self):
        seite = Seite({"appointment/with-action-state": {"status": 500}})
        with pytest.raises(RuntimeError, match="HTTP 500"):
            ansetzungen.hole_ansetzungen(seite, "S", date(2026, 7, 1), date(2027, 7, 1))

    @pytest.mark.parametrize("methode, pfad", [
        ("POST", "appointment/with-action-state"),
        ("GET", "venue/query"),
        ("POST", "appointment/SPIEL1/confirm"),
        ("DELETE", "match"),
        ("GET", "referee/SCHIRI42/history"),
        ("POST", "referee/SCHIRI42"),
        ("GET", "referee-id-card/SCHIRI42/photo"),
        ("GET", "league/../referee"),
    ])
    def test_nur_freigegebene_abrufe(self, methode, pfad):
        with pytest.raises(ValueError, match="nicht freigegeben"):
            sria_api._pruefe_abruf(methode, pfad)


class TestWarteAufApp:
    def test_liefert_schiri_id_aus_der_adresse(self):
        seite = Seite()
        assert warte_auf_app(seite) == "SCHIRI42"
        assert seite.wait_function_aufrufe == [sria_api._APP_BEREIT_JS]

    def test_adresse_ohne_schiri(self):
        with pytest.raises(RuntimeError, match="Schiedsrichter-ID"):
            warte_auf_app(Seite(url="https://sria.dfbnet.org/"))


class TestHilfen:
    def test_datum_de(self):
        assert datum_de("2019-01-26") == "26.01.2019"
        assert datum_de("2029-02-25T00:00:00") == "25.02.2029"
        assert datum_de(None) == ""

    @pytest.mark.parametrize("methode, pfad", [
        ("GET", "referee/SCHIRI42"),
        ("GET", "referee/SCHIRI42/qualification"),
        ("GET", "referee-id-card/SCHIRI42"),
        ("GET", "appointment/with-match-details"),
        ("GET", "appointment/summary"),
        ("GET", "season"),
    ])
    def test_lesepfade_sind_frei(self, methode, pfad):
        assert sria_api._pruefe_abruf(methode, pfad).endswith(pfad)
