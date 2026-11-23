"""Saisonrechnung im DFBnet-Format ("25/26" = 01.07.2025 bis 30.06.2026)."""
from datetime import date, datetime

import pytest

from utils import saison_utils
from utils.saison_utils import (
    parse_deutsches_datum,
    saison_fuer_datum,
    saison_start_jahr,
    saison_zeitraum,
)


def _heute_einfrieren(monkeypatch, tag: date):
    """Ersetzt date.today() im Modul, ohne den Konstruktor zu verlieren."""

    class FesterTag(date):
        @classmethod
        def today(cls):
            return tag

    monkeypatch.setattr(saison_utils, "date", FesterTag)


HEUTE = date(2026, 11, 23)


class TestSaisonStartJahr:
    @pytest.mark.parametrize("saison, erwartet", [
        ("25/26", 2025),
        ("26/27", 2026),
        ("00/01", 2000),
        ("09/10", 2009),
        ("99/00", 1999),
        ("95/96", 1995),
        (" 25/26 ", 2025),
        ("25/26\n", 2025),
    ])
    def test_parsen(self, saison, erwartet):
        assert saison_start_jahr(saison, HEUTE) == erwartet

    @pytest.mark.parametrize("saison, erwartet", [
        # Grenze: bis ein Jahr nach dem laufenden (2026 -> 27) gilt 20xx
        ("27/28", 2027),
        ("28/29", 1928),
        ("50/51", 1950),
    ])
    def test_jahrhundertgrenze(self, saison, erwartet):
        assert saison_start_jahr(saison, HEUTE) == erwartet

    @pytest.mark.parametrize("heute, saison, erwartet", [
        (date(2026, 6, 30), "27/28", 2027),
        (date(2026, 7, 1), "27/28", 2027),
        (date(2027, 1, 1), "28/29", 2028),
        (date(2030, 1, 1), "31/32", 2031),
        (date(2030, 1, 1), "32/33", 1932),
    ])
    def test_grenze_wandert_mit_dem_jahr(self, heute, saison, erwartet):
        assert saison_start_jahr(saison, heute) == erwartet

    @pytest.mark.parametrize("saison", [
        "", None, "2025/26", "25/2026", "2025/2026", "25-26", "25 / 26", "2526",
        "5/6", "ab/cd", "25/26/27", "Saison 25/26",
    ])
    def test_ungueltig(self, saison):
        assert saison_start_jahr(saison, HEUTE) is None

    def test_ohne_heute_nimmt_heutiges_datum(self, monkeypatch):
        _heute_einfrieren(monkeypatch, date(2026, 11, 23))
        assert saison_start_jahr("27/28") == 2027
        assert saison_start_jahr("28/29") == 1928

    def test_jahrhundertwechsel(self):
        assert saison_start_jahr("99/00", date(2099, 11, 1)) == 2099


class TestSaisonFuerDatum:
    @pytest.mark.parametrize("tag, erwartet", [
        (date(2026, 6, 30), "25/26"),
        (date(2026, 7, 1), "26/27"),
        (date(2026, 1, 1), "25/26"),
        (date(2025, 12, 31), "25/26"),
        (date(2026, 3, 15), "25/26"),
        (date(2026, 11, 23), "26/27"),
        (date(1999, 12, 31), "99/00"),
        (date(2000, 6, 30), "99/00"),
        (date(2000, 7, 1), "00/01"),
        (date(2009, 7, 1), "09/10"),
        (date(1995, 8, 1), "95/96"),
        (date(2024, 2, 29), "23/24"),
    ])
    def test_zuordnung(self, tag, erwartet):
        assert saison_fuer_datum(tag) == erwartet

    def test_datetime_wird_akzeptiert(self):
        assert saison_fuer_datum(datetime(2026, 7, 1, 0, 0)) == "26/27"
        assert saison_fuer_datum(datetime(2026, 6, 30, 23, 59)) == "25/26"

    @pytest.mark.parametrize("tag", [
        date(2026, 6, 30), date(2026, 7, 1), date(1999, 12, 31), date(2020, 1, 1),
    ])
    def test_rundlauf_mit_zeitraum(self, monkeypatch, tag):
        _heute_einfrieren(monkeypatch, HEUTE)
        beginn, ende = saison_zeitraum(saison_fuer_datum(tag))
        assert beginn <= tag <= ende


class TestSaisonZeitraum:
    @pytest.fixture(autouse=True)
    def heute(self, monkeypatch):
        _heute_einfrieren(monkeypatch, HEUTE)

    @pytest.mark.parametrize("saison, erwartet", [
        ("25/26", (date(2025, 7, 1), date(2026, 6, 30))),
        ("26/27", (date(2026, 7, 1), date(2027, 6, 30))),
        ("99/00", (date(1999, 7, 1), date(2000, 6, 30))),
        ("00/01", (date(2000, 7, 1), date(2001, 6, 30))),
        ("27/28", (date(2027, 7, 1), date(2028, 6, 30))),
        ("28/29", (date(1928, 7, 1), date(1929, 6, 30))),
    ])
    def test_zeitraum(self, saison, erwartet):
        assert saison_zeitraum(saison) == erwartet

    @pytest.mark.parametrize("saison", ["", None, "2025/26", "Saison", "25-26"])
    def test_ungueltig(self, saison):
        assert saison_zeitraum(saison) is None

    def test_rueckgabe_sind_echte_daten(self):
        beginn, ende = saison_zeitraum("25/26")
        assert beginn == date(2025, 7, 1) and isinstance(beginn, date)
        assert (ende - beginn).days == 364


class TestParseDeutschesDatum:
    @pytest.mark.parametrize("text, erwartet", [
        ("26.01.2019", date(2019, 1, 26)),
        (" 26.01.2019 ", date(2019, 1, 26)),
        ("01.07.2025", date(2025, 7, 1)),
        ("29.02.2024", date(2024, 2, 29)),
        ("31.12.1999", date(1999, 12, 31)),
        ("26.1.2019", date(2019, 1, 26)),   # strptime nimmt einstellige Felder
    ])
    def test_gueltig(self, text, erwartet):
        assert parse_deutsches_datum(text) == erwartet

    @pytest.mark.parametrize("text", [
        "", None, "   ", "31.02.2019", "29.02.2023", "32.01.2019", "26.13.2019",
        "2019-01-26", "26/01/2019", "26.01.19", "26.01.2019 15:00", "heute",
    ])
    def test_ungueltig(self, text):
        assert parse_deutsches_datum(text) is None
