"""Pure helper functions for match data: file names, kick-off, date columns."""
import pytest

from utils.match_utils import (
    extract_iso_date_from_anpfiff,
    generate_filename_from_match,
    parse_anpfiff,
    parse_saison_datum,
    sanitize_team_name,
)

ANPFIFF = "Samstag · 08.11.2025 · 13:00 Uhr"


def _match(**spiel_info):
    return {"spiel_info": spiel_info}


class TestDateiname:
    def test_normalfall(self):
        match = _match(heim_team="FC Bayern", gast_team="BVB", anpfiff=ANPFIFF)
        assert generate_filename_from_match(match) == "Spesen_FC Bayern_vs_BVB_08-11-2025.docx"

    def test_slash_im_teamnamen(self):
        match = _match(heim_team="SG A/B", gast_team="C/D/E", anpfiff=ANPFIFF)
        assert generate_filename_from_match(match) == "Spesen_SG A-B_vs_C-D-E_08-11-2025.docx"

    def test_kein_slash_im_ergebnis(self):
        match = _match(heim_team="A/B", gast_team="C/D", anpfiff=ANPFIFF)
        assert "/" not in generate_filename_from_match(match)

    @pytest.mark.parametrize("anpfiff", ["", "kein Datum", "Samstag · 8.11.2025 · 13:00 Uhr"])
    def test_ohne_erkennbares_datum(self, anpfiff):
        match = _match(heim_team="A", gast_team="B", anpfiff=anpfiff)
        assert generate_filename_from_match(match) == "Spesen_A_vs_B_01-01-2000.docx"

    def test_ohne_anpfiff_schluessel(self):
        assert generate_filename_from_match(_match(heim_team="A", gast_team="B")) == \
            "Spesen_A_vs_B_01-01-2000.docx"

    def test_datum_irgendwo_im_text(self):
        match = _match(heim_team="A", gast_team="B", anpfiff="am 24.12.2026 um 10")
        assert generate_filename_from_match(match) == "Spesen_A_vs_B_24-12-2026.docx"

    @pytest.mark.parametrize("heim, gast", [
        ("", ""), ("", "B"), ("A", ""), (None, None), ("   ", "B"), ("A", "  "),
    ])
    def test_turnier_ohne_teams(self, heim, gast):
        match = _match(heim_team=heim, gast_team=gast, anpfiff=ANPFIFF)
        assert generate_filename_from_match(match) == "Spesen_Turnier_08-11-2025_13-00.docx"

    def test_turnier_verschiedene_anstosszeiten_verschiedene_namen(self):
        a = _match(anpfiff="Samstag · 08.11.2025 · 10:00 Uhr")
        b = _match(anpfiff="Samstag · 08.11.2025 · 14:30 Uhr")
        assert generate_filename_from_match(a) != generate_filename_from_match(b)

    def test_turnier_ohne_zeit(self):
        assert generate_filename_from_match(_match(anpfiff="")) == \
            "Spesen_Turnier_01-01-2000_ohne-Zeit.docx"

    def test_leeres_match(self):
        assert generate_filename_from_match({}) == "Spesen_Turnier_01-01-2000_ohne-Zeit.docx"

    @pytest.mark.parametrize("spielklasse, mannschaftsart, staffel", [
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
        ("Oberliga", "Herren", "NOFV-Oberliga Süd"),
        ("Regionalliga Nordost", "B-Junioren", "Regionalliga Nordost"),
    ])
    def test_nofv_pflichtspiel_ist_xlsx(self, spielklasse, mannschaftsart, staffel):
        match = _match(heim_team="A", gast_team="B", anpfiff=ANPFIFF,
                       spielklasse=spielklasse, mannschaftsart=mannschaftsart, staffel=staffel)
        assert generate_filename_from_match(match) == "Spesen_A_vs_B_08-11-2025.xlsx"

    def test_nofv_turnier_ist_xlsx(self):
        match = _match(anpfiff=ANPFIFF, spielklasse="Regionalliga Nordost",
                       mannschaftsart="Herren", staffel="Regionalliga Nordost")
        assert generate_filename_from_match(match) == "Spesen_Turnier_08-11-2025_13-00.xlsx"

    @pytest.mark.parametrize("spielklasse, mannschaftsart, staffel", [
        ("Verbandsliga", "Herren", "Thüringenliga"),
        ("Oberliga", "Herren", "Oberliga Niedersachsen"),
        ("Regionalliga Nordost", "Herren Ü35", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "C-Junioren", "Aufstiegsspiel zur NOFV-CJRL Regionalliga"),
        (None, None, None),
    ])
    def test_sonst_docx(self, spielklasse, mannschaftsart, staffel):
        match = _match(heim_team="A", gast_team="B", anpfiff=ANPFIFF,
                       spielklasse=spielklasse, mannschaftsart=mannschaftsart, staffel=staffel)
        assert generate_filename_from_match(match).endswith(".docx")

    def test_anpfiff_none(self):
        match = _match(heim_team="A", gast_team="B", anpfiff=None)
        assert generate_filename_from_match(match) == "Spesen_A_vs_B_01-01-2000.docx"


class TestParseAnpfiff:
    @pytest.mark.parametrize("text, erwartet", [
        (ANPFIFF, ("08.11.2025", "13:00")),
        ("Sonntag · 01.06.2026 · 09:30 Uhr", ("01.06.2026", "09:30")),
        ("Samstag·08.11.2025·13:00Uhr", ("08.11.2025", "13:00")),
        ("Samstag · 08.11.2025 · 13:00", ("08.11.2025", "13:00")),
        ("a · b · c · d", ("b", "c")),
    ])
    def test_gueltig(self, text, erwartet):
        assert parse_anpfiff(text) == erwartet

    @pytest.mark.parametrize("text", ["", "08.11.2025", "Samstag · 08.11.2025", "kaputt"])
    def test_zu_wenige_teile_gibt_eingabe_zurueck(self, text):
        assert parse_anpfiff(text) == (text, "")

    def test_none_wirft_nicht(self):
        _, uhrzeit = parse_anpfiff(None)
        assert uhrzeit == ""


class TestIsoDatum:
    @pytest.mark.parametrize("text, erwartet", [
        (ANPFIFF, "2025-11-08"),
        ("31.12.1999", "1999-12-31"),
        ("Sonntag · 01.06.2026 · 09:30 Uhr", "2026-06-01"),
        ("am 24.12.2026", "2026-12-24"),
    ])
    def test_gueltig(self, text, erwartet):
        assert extract_iso_date_from_anpfiff(text) == erwartet

    @pytest.mark.parametrize("text", ["", "kaputt", "8.11.2025", "08.11.25", "08-11-2025"])
    def test_ungueltig(self, text):
        assert extract_iso_date_from_anpfiff(text) == "1900-01-01"

    def test_sortierbar(self):
        daten = ["Mo · 02.01.2026 · 10:00 Uhr", "Mo · 31.12.2025 · 10:00 Uhr",
                 "Mo · 15.06.2026 · 10:00 Uhr"]
        sortiert = sorted(daten, key=extract_iso_date_from_anpfiff)
        assert [extract_iso_date_from_anpfiff(d) for d in sortiert] == \
            ["2025-12-31", "2026-01-02", "2026-06-15"]

    def test_none(self):
        assert extract_iso_date_from_anpfiff(None) == "1900-01-01"


class TestSanitizeTeamName:
    @pytest.mark.parametrize("name, erwartet", [
        ("FC Bayern", "FC Bayern"),
        ("SG A/B", "SG A-B"),
        ("A\\B", "A-B"),
        ("A:B", "A-B"),
        ("A|B", "A-B"),
        ('A*B?C"D<E>F', "ABCDEF"),
        ("  FC Bayern  ", "FC Bayern"),
        ("FC Rot-Weiß Erfurt", "FC Rot-Weiß Erfurt"),
        ('a/b\\c:d*e?f"g<h>i|j', "a-b-c-defghi-j"),
    ])
    def test_bereinigung(self, name, erwartet):
        assert sanitize_team_name(name) == erwartet

    @pytest.mark.parametrize("name", ["", None])
    def test_leer_wird_unbekannt(self, name):
        assert sanitize_team_name(name) == "Unbekannt"

    @pytest.mark.parametrize("name", ["   ", "***", "?<>"])
    def test_bereinigt_leer_wird_unbekannt(self, name):
        assert sanitize_team_name(name) == "Unbekannt"


class TestParseSaisonDatum:
    @pytest.mark.parametrize("text, erwartet", [
        ("20.09.26, 15:00", ("2026-09-20", "15:00")),
        ("01.07.25, 9:30", ("2025-07-01", "9:30")),
        ("31.12.99, 23:59", ("2099-12-31", "23:59")),   # two-digit is always 20xx
        ("20.09.26", ("2026-09-20", "")),
        ("Sa, 20.09.26 15:00", ("2026-09-20", "15:00")),
    ])
    def test_gueltig(self, text, erwartet):
        assert parse_saison_datum(text) == erwartet

    @pytest.mark.parametrize("text, uhrzeit", [
        # A four-digit year does not belong in this column
        ("20.09.2026, 15:00", "15:00"),
        ("", ""),
        (None, ""),
        ("kaputt", ""),
        ("1.9.26, 9:30", "9:30"),
        ("15:00", "15:00"),
    ])
    def test_ungueltig(self, text, uhrzeit):
        assert parse_saison_datum(text) == ("1900-01-01", uhrzeit)
