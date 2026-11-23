"""
NOFV-Reisekostenabrechnung (XLSX): ein Blatt je angesetzter Person.

Die Mappe entsteht im Speicher aus der echten Vorlage und wird mit openpyxl
wieder geoeffnet. Formeln rechnet openpyxl nicht aus - geprueft werden deshalb
die eingetragenen Werte und dass die Formeln an ihrem Platz stehen.
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from generator.docx_generator import KM_SATZ_EURO
from generator.nofv_generator import (
    DATUMSFORMAT,
    FORMEL_GESAMT,
    FORMEL_PKW,
    ZELLEN_SCHRUMPFEN,
    NofvGenerator,
    _datum,
    _ort_aus_adresse,
    _ort_aus_plz_ort,
    betrag_in_worten,
    zahl_in_worten,
)

VORLAGE = Path(__file__).resolve().parent.parent / "src" / "data" / "SR-Reisekostenabrechnung_NOFV.xlsx"


def _spiel(**ueberschreiben) -> dict:
    """Ein NOFV-Pflichtspiel in der Form, die db.matches.get_match liefert."""
    spiel = {
        "spiel_info": {
            "heim_team": "FC Carl Zeiss Jena",
            "gast_team": "BSG Chemie Leipzig",
            "anpfiff": "Samstag · 08.11.2025 · 13:00 Uhr",
            "spielklasse": "Regionalliga Nordost",
            "mannschaftsart": "Herren",
            "staffel": "Regionalliga Nordost",
        },
        "spielstaette": {
            "name": "Ernst-Abbe-Sportfeld",
            "adresse": "Oberaue 3, 07745 Jena",
        },
        "schiedsrichter": [
            {"rolle": "SR", "name": "Max Mustermann", "strasse": "Hauptstr. 1", "plz_ort": "99438 Bad Berka"},
            {"rolle": "SRA 1", "name": "Eva Maria Muster", "strasse": "Nebenweg 2", "plz_ort": "99423 Weimar"},
            {"rolle": "SRA 2", "name": "Karl Beispiel", "strasse": "Gasse 3", "plz_ort": "99510 Apolda"},
        ],
    }
    spiel.update(ueberschreiben)
    return spiel


@pytest.fixture(scope="module")
def generator():
    return NofvGenerator(VORLAGE)


def _mappe(generator, spiel, expenses=None):
    return load_workbook(BytesIO(generator.render_workbook(spiel, expenses)))


# ===== Zahlwoerter =====

class TestZahlInWorten:
    @pytest.mark.parametrize("zahl, wort", [
        (0, "null"),
        (1, "eins"),
        (2, "zwei"),
        (11, "elf"),
        (16, "sechzehn"),
        (17, "siebzehn"),
        (20, "zwanzig"),
        (21, "einundzwanzig"),
        (30, "dreißig"),
        (99, "neunundneunzig"),
        (100, "einhundert"),
        (101, "einhunderteins"),
        (110, "einhundertzehn"),
        (310, "dreihundertzehn"),
        (1000, "eintausend"),
        (1001, "eintausendeins"),
        (2021, "zweitausendeinundzwanzig"),
        (999999, "neunhundertneunundneunzigtausendneunhundertneunundneunzig"),
    ])
    def test_zahlwort(self, zahl, wort):
        assert zahl_in_worten(zahl) == wort

    @pytest.mark.parametrize("betrag, text", [
        (310.5, "dreihundertzehn Euro fünfzig Cent"),
        (1.0, "ein Euro"),
        (1.01, "ein Euro ein Cent"),
        (101.0, "einhunderteins Euro"),
        (0.0, "null Euro"),
        (0.5, "null Euro fünfzig Cent"),
        (330.0, "dreihundertdreißig Euro"),
        (42.99, "zweiundvierzig Euro neunundneunzig Cent"),
    ])
    def test_betrag(self, betrag, text):
        assert betrag_in_worten(betrag) == text

    def test_betrag_rundet_auf_cent(self):
        # 0.1 + 0.2 ist in Gleitkomma 0.30000000000000004
        assert betrag_in_worten(0.1 + 0.2) == "null Euro dreißig Cent"


# ===== Hilfen =====

class TestHilfen:
    def test_ort_aus_plz_ort(self):
        assert _ort_aus_plz_ort("99438 Bad Berka") == "Bad Berka"
        assert _ort_aus_plz_ort("Bad Berka") == "Bad Berka"
        assert _ort_aus_plz_ort("") == ""
        assert _ort_aus_plz_ort(None) == ""

    def test_ort_aus_adresse(self):
        assert _ort_aus_adresse("Am Sportzentrum 17, 06792 Sandersdorf") == "Sandersdorf"
        assert _ort_aus_adresse("Ohne Postleitzahl") == ""
        assert _ort_aus_adresse(None) == ""

    def test_datum(self):
        assert _datum("Samstag · 08.11.2025 · 13:00 Uhr").isoformat() == "2025-11-08"
        assert _datum("") is None
        assert _datum(None) is None
        assert _datum("irgendwann") is None


# ===== Blaetter =====

class TestBlaetter:
    def test_fehlende_vorlage(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            NofvGenerator(tmp_path / "gibtsnicht.xlsx")

    def test_ein_blatt_je_person(self, generator):
        assert _mappe(generator, _spiel()).sheetnames == ["SR", "SRA 1", "SRA 2"]

    def test_nur_schiedsrichter(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = spiel["schiedsrichter"][:1]
        assert _mappe(generator, spiel).sheetnames == ["SR"]

    def test_formularreihenfolge_unabhaengig_von_eingabe(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = list(reversed(spiel["schiedsrichter"]))
        mappe = _mappe(generator, spiel)
        assert mappe.sheetnames == ["SR", "SRA 1", "SRA 2"]
        assert mappe["SR"]["E8"].value == "Mustermann, Max"

    def test_person_ohne_namen_bekommt_kein_blatt(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"][2]["name"] = ""
        assert _mappe(generator, spiel).sheetnames == ["SR", "SRA 1"]

    def test_nur_assistent(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = spiel["schiedsrichter"][1:2]
        mappe = _mappe(generator, spiel)
        assert mappe.sheetnames == ["SRA 1"]
        assert mappe["SRA 1"]["E12"].value == "Schiedsrichterassistent 1"
        assert mappe["SRA 1"]["J20"].value == 150

    def test_ohne_ansetzung_ein_leeres_schiedsrichterblatt(self, generator):
        mappe = _mappe(generator, _spiel(schiedsrichter=[]))
        assert mappe.sheetnames == ["SR"]
        blatt = mappe["SR"]
        assert blatt["E8"].value is None
        assert blatt["E12"].value is None
        # Die Spieldaten stehen trotzdem da
        assert blatt["E14"].value == "FC Carl Zeiss Jena"
        assert blatt["J20"].value == 300

    def test_jedes_blatt_mit_logo_und_druckbereich(self, generator):
        mappe = _mappe(generator, _spiel())
        for blatt in mappe:
            assert len(blatt._images) == 1
            assert blatt.print_area == f"'{blatt.title}'!$A$1:$J$48"

    def test_mehrfach_rendern_ohne_seiteneffekt(self, generator):
        # Die Vorlage wird je Aufruf neu geladen, Blaetter haeufen sich nicht an
        _mappe(generator, _spiel())
        assert _mappe(generator, _spiel()).sheetnames == ["SR", "SRA 1", "SRA 2"]


# ===== Zellen =====

class TestZellen:
    def test_person(self, generator):
        mappe = _mappe(generator, _spiel())
        erwartet = {
            "SR": ("Mustermann, Max", "Hauptstr. 1", "99438 Bad Berka", "Schiedsrichter"),
            "SRA 1": ("Muster, Eva Maria", "Nebenweg 2", "99423 Weimar", "Schiedsrichterassistent 1"),
            "SRA 2": ("Beispiel, Karl", "Gasse 3", "99510 Apolda", "Schiedsrichterassistent 2"),
        }
        for titel, (name, strasse, wohnort, einsatz) in erwartet.items():
            blatt = mappe[titel]
            assert blatt["E8"].value == name
            assert blatt["E9"].value == strasse
            assert blatt["E10"].value == wohnort
            assert blatt["E12"].value == einsatz

    def test_spieldaten_auf_jedem_blatt(self, generator):
        mappe = _mappe(generator, _spiel(spielnummer="123456"))
        for blatt in mappe:
            assert blatt["E13"].value == "Regionalliga Nordost"
            assert blatt["E14"].value == "FC Carl Zeiss Jena"
            assert blatt["I14"].value == "BSG Chemie Leipzig"
            assert blatt["J15"].value == "123456"

    def test_ohne_spielnummer_leer(self, generator):
        assert _mappe(generator, _spiel())["SR"]["J15"].value is None

    def test_staffel_vor_spielklasse(self, generator):
        spiel = _spiel()
        spiel["spiel_info"]["staffel"] = "Regionalliga Nordost Süd"
        assert _mappe(generator, spiel)["SR"]["E13"].value == "Regionalliga Nordost Süd"

    def test_ohne_staffel_die_spielklasse(self, generator):
        spiel = _spiel(sr_spesen=300.0, sra_spesen=150.0)
        spiel["spiel_info"]["staffel"] = ""
        assert _mappe(generator, spiel)["SR"]["E13"].value == "Regionalliga Nordost"

    def test_datum_hin_und_rueckreise(self, generator):
        blatt = _mappe(generator, _spiel())["SR"]
        for zelle in ("E15", "E16", "E17"):
            assert blatt[zelle].value == datetime(2025, 11, 8)
            assert blatt[zelle].number_format == DATUMSFORMAT

    def test_ohne_datum_keine_datumsfelder(self, generator):
        spiel = _spiel()
        spiel["spiel_info"]["anpfiff"] = ""
        blatt = _mappe(generator, spiel)["SR"]
        for zelle in ("E15", "E16", "E17"):
            assert blatt[zelle].value is None

    def test_strecke_vom_wohnort_zum_spielort(self, generator):
        mappe = _mappe(generator, _spiel())
        assert mappe["SR"]["I16"].value == "Bad Berka - Jena"
        assert mappe["SR"]["I17"].value == "Jena - Bad Berka"
        assert mappe["SRA 1"]["I16"].value == "Weimar - Jena"

    def test_strecke_mit_staettenname_ohne_plz(self, generator):
        spiel = _spiel(spielstaette={"name": "Ernst-Abbe-Sportfeld", "adresse": "Oberaue 3"})
        assert _mappe(generator, spiel)["SR"]["I16"].value == "Bad Berka - Ernst-Abbe-Sportfeld"

    def test_ohne_wohnort_keine_strecke(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"][0]["plz_ort"] = ""
        blatt = _mappe(generator, spiel)["SR"]
        assert blatt["I16"].value is None
        assert blatt["I17"].value is None

    def test_aufwand_nach_nofv_finanzordnung(self, generator):
        mappe = _mappe(generator, _spiel())
        assert mappe["SR"]["J20"].value == 300
        assert mappe["SRA 1"]["J20"].value == 150
        assert mappe["SRA 2"]["J20"].value == 150

    def test_eingefrorene_saetze_gewinnen(self, generator):
        mappe = _mappe(generator, _spiel(sr_spesen=111.0, sra_spesen=55.5))
        assert mappe["SR"]["J20"].value == 111
        assert mappe["SRA 1"]["J20"].value == 55.5

    def test_ohne_satz_kein_aufwand_und_keine_worte(self, generator):
        mappe = _mappe(generator, _spiel(sr_spesen=None, sra_spesen=None), {"sr_km": 100})
        assert mappe["SR"]["J20"].value is None
        assert mappe["SR"]["E32"].value is None

    def test_formeln_bleiben_formeln(self, generator):
        for blatt in _mappe(generator, _spiel()):
            assert blatt["J26"].value == FORMEL_PKW
            assert blatt["J31"].value == FORMEL_GESAMT

    def test_km_satz_standard(self, generator):
        assert _mappe(generator, _spiel())["SR"]["G26"].value == KM_SATZ_EURO

    def test_km_satz_eingefroren(self, generator):
        mappe = _mappe(generator, _spiel(km_satz=0.35), {"sr_km": 100})
        assert mappe["SR"]["G26"].value == 0.35
        assert mappe["SR"]["E32"].value == "dreihundertfünfunddreißig Euro"

    def test_freitextfelder_schrumpfen(self, generator):
        blatt = _mappe(generator, _spiel())["SR"]
        for zelle in ZELLEN_SCHRUMPFEN:
            assert blatt[zelle].alignment.shrink_to_fit is True
            assert blatt[zelle].alignment.vertical is not None


# ===== Fahrtkosten =====

class TestFahrtkosten:
    def test_ohne_fahrtkosten_nichts_eingetragen(self, generator):
        blatt = _mappe(generator, _spiel())["SR"]
        assert blatt["E26"].value is None
        assert blatt["J24"].value is None
        assert blatt["E32"].value is None

    def test_kilometer_und_bahn_je_person(self, generator):
        expenses = {"sr_km": 100, "sra1_oevm": 12.5, "sra2_km": 40, "sra2_oevm": 7.2}
        mappe = _mappe(generator, _spiel(), expenses)

        assert mappe["SR"]["E26"].value == 100
        assert mappe["SR"]["J24"].value is None
        assert mappe["SR"]["E32"].value == "dreihundertdreißig Euro"

        assert mappe["SRA 1"]["E26"].value is None
        assert mappe["SRA 1"]["J24"].value == 12.5
        assert mappe["SRA 1"]["E32"].value == "einhundertzweiundsechzig Euro fünfzig Cent"

        assert mappe["SRA 2"]["E26"].value == 40
        assert mappe["SRA 2"]["J24"].value == 7.2
        # 150 + 12,00 + 7,20
        assert mappe["SRA 2"]["E32"].value == "einhundertneunundsechzig Euro zwanzig Cent"

    def test_null_kilometer_werden_eingetragen(self, generator):
        # Sonst bliebe die Gesamt-Formel leer, obwohl alles erfasst ist
        blatt = _mappe(generator, _spiel(), {"sr_km": 0})["SR"]
        assert blatt["E26"].value == 0
        assert blatt["E32"].value == "dreihundert Euro"

    def test_null_kilometer_neben_bahn_bleiben_leer(self, generator):
        blatt = _mappe(generator, _spiel(), {"sr_km": 0, "sr_oevm": 5})["SR"]
        assert blatt["E26"].value is None
        assert blatt["J24"].value == 5
        assert blatt["E32"].value == "dreihundertfünf Euro"

    @pytest.mark.xfail(strict=True, reason=(
        "0 € OeVM ohne km gilt als erfasst und fuellt 'In Worten', traegt aber "
        "weder E26 noch J24 ein - die Gesamt-Formel bleibt leer"
    ))
    def test_null_bahn_ohne_kilometer_fuellt_die_summe(self, generator):
        blatt = _mappe(generator, _spiel(), {"sr_oevm": 0})["SR"]
        assert blatt["E32"].value == "dreihundert Euro"
        # Mindestens eins der beiden Felder muss die 0 tragen, sonst ergibt
        # FORMEL_GESAMT "" - neben einem ausgefuellten Betrag in Worten
        assert blatt["E26"].value == 0 or blatt["J24"].value == 0

    def test_fremde_rollen_beeinflussen_blatt_nicht(self, generator):
        mappe = _mappe(generator, _spiel(), {"sra2_km": 99})
        assert mappe["SR"]["E26"].value is None
        assert mappe["SRA 1"]["E26"].value is None
        assert mappe["SRA 2"]["E26"].value == 99

    def test_none_expenses_wie_leer(self, generator):
        a = _mappe(generator, _spiel(), None)["SR"]
        b = _mappe(generator, _spiel(), {})["SR"]
        for zelle in ("E26", "J24", "E32", "J20"):
            assert a[zelle].value == b[zelle].value
