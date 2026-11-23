"""
Spesenrechner nach TFV-Spesenordnung §2 und NOFV-Finanzordnung §9 Nr. 7.

Geldkritisch. Leitlinie der App: wo der Satz nicht eindeutig feststeht,
kommt (None, None) heraus - nie ein geratener Betrag. Diese Faelle sind hier
ausdruecklich abgedeckt.
"""
import pytest

from generator import spesen_calculator as sc
from generator.spesen_calculator import (
    FREUNDSCHAFTSSPIEL,
    NOFV_A_JUNIOREN_REGIONALLIGA,
    NOFV_BC_JUNIOREN_REGIONALLIGA,
    NOFV_FRAUEN_REGIONALLIGA,
    NOFV_HERREN_OBERLIGA,
    NOFV_HERREN_REGIONALLIGA,
    POKALSPIEL,
    PUNKTSPIEL,
    SPESEN_NOFV,
    calculate_spesen,
    format_spesen,
    is_alte_herren,
    ist_nofv_spiel,
    nofv_spielklasse,
    wettbewerbsart,
)

LEER = (None, None)


# ===== Ligatabellen fuer Pokal/Freundschaft =====

def _staffel(spielklasse, staffel_id, mannschaften, verband="thueringen"):
    """Legt eine Staffel samt Tabelle ueber den echten Schreibweg an."""
    from db.ligen import ersetze_staffel
    from scraper.fussball_de import Staffel, Tabellenplatz

    staffel = Staffel(
        staffel_id=staffel_id,
        pfad=f"/spieltagsuebersicht/test/-/staffel/{staffel_id}",
        slug=staffel_id.lower(),
        spielklasse=spielklasse,
        verband=verband,
        anzeigename=f"{spielklasse.title()} {staffel_id}",
    )
    tabelle = [
        Tabellenplatz(platz=i + 1, mannschaft=name, team_id=f"{staffel_id}-T{i}",
                      spiele=0, siege=0, unentschieden=0, niederlagen=0,
                      tore=0, gegentore=0, punkte=0)
        for i, name in enumerate(mannschaften)
    ]
    ersetze_staffel(staffel, tabelle)


@pytest.fixture
def ligen(db):
    """
    Thueringer Landesebene plus ueberregionale Tabellen:
    - Verbandsliga: FC Saalfeld, SV 09 Arnstadt
    - Landesklasse: FC Empor Weimar 06, SV Germania Ilmenau, FC Saalfeld 2.
    - Oberliga:     FC Carl Zeiss Jena II
    - Regionalliga: FC Rot-Weiss Erfurt
    """
    _staffel("verbandsliga", "VL1", ["FC Saalfeld", "SV 09 Arnstadt"])
    _staffel("landesklasse", "LK1", ["FC Empor Weimar 06", "SV Germania Ilmenau",
                                    "FC Saalfeld 2."])
    _staffel("oberliga", "OL1", ["FC Carl Zeiss Jena II"], verband="nofv")
    _staffel("regionalliga", "RL1", ["FC Rot-Weiss Erfurt"], verband="nofv")
    return db


@pytest.fixture
def ligen_ohne_ueberregional(db):
    """Nur Thueringer Landesebene - die ueberregionalen Tabellen fehlen."""
    _staffel("verbandsliga", "VL1", ["FC Saalfeld"])
    _staffel("landesklasse", "LK1", ["FC Empor Weimar 06"])
    return db


# ===== wettbewerbsart =====

class TestWettbewerbsart:
    @pytest.mark.parametrize("spielklasse, erwartet", [
        ("Kreispokal", POKALSPIEL),
        ("Landespokal", POKALSPIEL),
        ("POKAL", POKALSPIEL),
        ("Kreisfreundschaftsspiele", FREUNDSCHAFTSSPIEL),
        ("Freundschaftsspiele", FREUNDSCHAFTSSPIEL),
        ("Verbandsliga", PUNKTSPIEL),
        ("Kreisoberliga", PUNKTSPIEL),
        ("Hallen-Landesturnier", PUNKTSPIEL),
        ("Landesturnier", PUNKTSPIEL),
        ("", PUNKTSPIEL),
        (None, PUNKTSPIEL),
        # Pokal hat Vorrang, falls beide Woerter vorkommen
        ("Pokal-Freundschaftsturnier", POKALSPIEL),
    ])
    def test_zuordnung(self, spielklasse, erwartet):
        assert wettbewerbsart(spielklasse) == erwartet


# ===== Eingabepruefung =====

class TestFehlendeAngaben:
    @pytest.mark.parametrize("spielklasse, mannschaftsart", [
        ("", "Herren"),
        (None, "Herren"),
        ("Verbandsliga", ""),
        ("Verbandsliga", None),
        ("", ""),
        (None, None),
    ])
    def test_ohne_spielklasse_oder_mannschaftsart_leer(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == LEER

    @pytest.mark.parametrize("mannschaftsart", ["Unbekannt", "Bambini-Mix", "Futsal", "XYZ"])
    def test_unbekannte_mannschaftsart_leer(self, mannschaftsart):
        assert calculate_spesen("Kreisoberliga", mannschaftsart) == LEER


# ===== §2 Abs. 2a Maenner =====

class TestMaenner:
    @pytest.mark.parametrize("spielklasse, erwartet", [
        ("Verbandsliga", (50.00, 40.00)),
        ("Landesklasse", (40.00, 30.00)),
        ("Kreisoberliga", (30.00, 25.00)),
        ("Kreisliga", (25.00, 23.00)),
        ("Kreisklasse", (25.00, 23.00)),
        ("1.Kreisklasse", (25.00, 23.00)),
        ("2. Kreisklasse", (25.00, 23.00)),
        ("Kreisliga A", (25.00, 23.00)),
        # Gross-/Kleinschreibung egal
        ("VERBANDSLIGA", (50.00, 40.00)),
        ("kreisoberliga", (30.00, 25.00)),
        # Kreis-Fallback: alles mit "kreis" ohne Tabellenzeile
        ("Kreismeisterschaft", (25.00, 23.00)),
        ("Hallenkreismeisterschaft", (25.00, 23.00)),
    ])
    def test_tabelle(self, spielklasse, erwartet):
        assert calculate_spesen(spielklasse, "Herren") == erwartet

    @pytest.mark.parametrize("mannschaftsart", ["Herren", "Männer", "HERREN", "herren"])
    def test_schreibweisen_der_mannschaftsart(self, mannschaftsart):
        assert calculate_spesen("Verbandsliga", mannschaftsart) == (50.00, 40.00)

    def test_kreisoberliga_nicht_als_kreisliga(self):
        # "kreisoberliga" enthaelt "kreis" und "liga" - darf nicht 25/23 werden
        assert calculate_spesen("Kreisoberliga", "Herren") == (30.00, 25.00)

    def test_kreisoberliga_nicht_als_oberliga_ueberregional(self):
        # "Kreisoberliga" enthaelt "oberliga" - ist aber Kreisebene
        assert calculate_spesen("Kreisoberliga", "Herren") != LEER

    @pytest.mark.parametrize("spielklasse", [
        "Landesliga",          # gibt es bei den TFV-Herren nicht
        "Landesturnier",       # Herren-Turnier auf Landesebene: keine Zeile
        "Stadtliga",
        "Thüringenliga",       # Sponsorenname ohne "verbandsliga"
        "  ",
    ])
    def test_unbekannte_landesklasse_leer(self, spielklasse):
        assert calculate_spesen(spielklasse, "Herren") == LEER


# ===== §2 Abs. 2a Alte Herren =====

class TestAlteHerren:
    @pytest.mark.parametrize("mannschaftsart", [
        "Herren Ü32", "Herren Ü35", "Herren Ü40", "Herren Ü45", "Herren Ü50",
        "Herren Ü 40", "Alte Herren",
    ])
    @pytest.mark.parametrize("spielklasse", ["Kreisoberliga", "Kreisliga", "Kreisklasse"])
    def test_kreis_einheitlich(self, spielklasse, mannschaftsart):
        # Kreisoberliga Ue45 darf NICHT die 30/25 der Maenner bekommen
        assert calculate_spesen(spielklasse, mannschaftsart) == (25.00, 23.00)

    @pytest.mark.parametrize("spielklasse", [
        "Kreisliga Kleinfeld", "Kreis-Kleinfeld", "Kleinfeld Kreisklasse",
    ])
    def test_kreis_kleinfeld(self, spielklasse):
        assert calculate_spesen(spielklasse, "Herren Ü50") == (20.00, None)

    @pytest.mark.parametrize("spielklasse", [
        "Landesturnier", "Hallen-Landesturnier", "Landesmeisterschaft",
    ])
    def test_landesmeisterschaft(self, spielklasse):
        assert calculate_spesen(spielklasse, "Herren Ü35") == (40.00, 30.00)

    @pytest.mark.parametrize("spielklasse", ["Verbandsliga", "Landesklasse", "Landesliga"])
    def test_landesebene_ohne_meisterschaft_leer(self, spielklasse):
        # Keine Maenner-Tabelle fuer Alte Herren - lieber leer
        assert calculate_spesen(spielklasse, "Herren Ü40") == LEER

    @pytest.mark.parametrize("mannschaftsart, erwartet", [
        ("herren ü32", True),
        ("herren ü 35", True),
        ("herren ü50", True),
        ("alte herren", True),
        ("herren", False),
        ("männer", False),
        ("herren ü3", False),    # einstellig ist keine Altersklasse
        ("a-junioren", False),
    ])
    def test_is_alte_herren(self, mannschaftsart, erwartet):
        # Aufrufer reichen die Mannschaftsart kleingeschrieben herein
        assert bool(is_alte_herren(mannschaftsart)) is erwartet


# ===== §2 Abs. 2b Frauen/Juniorinnen =====

class TestFrauen:
    @pytest.mark.parametrize("spielklasse, erwartet", [
        ("Verbandsliga", (25.00, 20.00)),
        ("Landesklasse", (25.00, 20.00)),
        ("Kreisoberliga", (20.00, None)),
        ("Kreisliga", (20.00, None)),       # Kreis-Fallback
        ("Kreisklasse", (20.00, None)),
    ])
    @pytest.mark.parametrize("mannschaftsart", ["Frauen", "Damen"])
    def test_tabelle(self, spielklasse, mannschaftsart, erwartet):
        assert calculate_spesen(spielklasse, mannschaftsart) == erwartet

    @pytest.mark.parametrize("spielklasse", ["Landesliga", "Stadtliga", "Landesturnier"])
    def test_unbekannt_leer(self, spielklasse):
        assert calculate_spesen(spielklasse, "Frauen") == LEER

    @pytest.mark.parametrize("mannschaftsart", [
        "A-Juniorinnen", "B-Juniorinnen", "C-Juniorinnen", "D-Juniorinnen", "Mädchen",
    ])
    @pytest.mark.parametrize("spielklasse", [
        "Verbandsliga", "Landesklasse", "Landesliga", "Kreisoberliga", "Kreisliga",
        "Stadtliga", "Hallenturnier",
    ])
    def test_juniorinnen_immer_20_ohne_sra(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (20.00, None)


# ===== §2 Abs. 2c Junioren =====

class TestJunioren:
    @pytest.mark.parametrize("mannschaftsart", ["A-Junioren", "B-Junioren"])
    @pytest.mark.parametrize("spielklasse", ["Kreisoberliga", "Kreisliga", "1.Kreisklasse"])
    def test_kreis_a_b(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (23.00, 18.00)

    @pytest.mark.parametrize("mannschaftsart", [
        "C-Junioren", "D-Junioren", "E-Junioren", "F-Junioren", "G-Junioren",
    ])
    @pytest.mark.parametrize("spielklasse", ["Kreisoberliga", "Kreisliga", "Kreisklasse Kleinfeld"])
    def test_kreis_c_und_juenger(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (20.00, 15.00)

    @pytest.mark.parametrize("mannschaftsart", ["A-Junioren", "B-Junioren", "C-Junioren"])
    @pytest.mark.parametrize("spielklasse", [
        "Verbandsliga", "Landesklasse", "Landesliga", "Fair-Play-Liga", "Kinderfussball",
    ])
    def test_land_a_b_c(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (25.00, 20.00)

    @pytest.mark.parametrize("mannschaftsart", ["D-Junioren", "E-Junioren", "F-Junioren", "G-Junioren"])
    @pytest.mark.parametrize("spielklasse", ["Verbandsliga", "Landesklasse", "Landesliga"])
    def test_land_d_und_juenger(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (20.00, None)

    @pytest.mark.parametrize("mannschaftsart", ["A-Junioren", "B-Junioren", "C-Junioren"])
    @pytest.mark.parametrize("spielklasse", ["Talenteliga", "Landesliga Kleinfeld", "Kleinfeld"])
    def test_land_talenteliga_kleinfeld(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (20.00, None)

    @pytest.mark.parametrize("spielklasse", [
        "Stadtliga", "Landesmeisterschaft", "Hallenturnier", "Verbandsturnier",
    ])
    def test_land_ohne_tfv_spielklasse_leer(self, spielklasse):
        # Geschlossene Liste: fremde Landesverbaende nicht still mit 25/20 abrechnen
        assert calculate_spesen(spielklasse, "B-Junioren") == LEER

    @pytest.mark.parametrize("spielklasse", [
        "A-Junioren-Bundesliga", "B-Junioren-Bundesliga", "Nachwuchsliga",
        "Regionalliga", "Oberliga", "DFB-Nachwuchsliga",
    ])
    def test_ueberregional_leer(self, spielklasse):
        assert calculate_spesen(spielklasse, "A-Junioren") == LEER


# ===== Ueberregional =====

class TestUeberregional:
    @pytest.mark.parametrize("spielklasse", [
        "Bundesliga", "2. Bundesliga", "3. Liga DFB", "Regionalliga", "Regionalliga Nordost",
        "Oberliga", "NOFV-Oberliga", "Frauen-Bundesliga", "DFB-Pokal", "Nachwuchsliga",
    ])
    @pytest.mark.parametrize("mannschaftsart", ["Herren", "Frauen", "B-Junioren"])
    def test_ohne_nofv_staffel_leer(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == LEER

    @pytest.mark.parametrize("spielklasse", ["Kreisoberliga", "Kreisliga"])
    def test_kreis_nie_ueberregional(self, spielklasse):
        assert sc._is_ueberregional(spielklasse.lower()) is False


# ===== §2 Abs. 6 fremde Verbaende =====

class TestFremderVerband:
    @pytest.mark.parametrize("staffel", [
        "1. Altmark West Liga",
        "Kreisoberliga Sachsen-Anhalt",
        "Landesliga Hessen",
        "Brandenburgliga",
        "Bayernliga Nord",
        "Verbandsliga Württemberg",
        "Verbandsliga Wuerttemberg",
        "Niedersachsenliga",
        "Westfalenliga",
        "Oberliga Rheinland-Pfalz/Saar",
        "Saarlandliga",
        "Bremen-Liga",
        "Hamburg-Liga",
        "Schleswig-Holstein-Liga",
        "Verbandsliga Mecklenburg-Vorpommern",
        "Berlin-Liga",
        "Mittelrheinliga",
        "Niederrheinliga",
        "Rheinlandliga",
        "U14-Talente-Spielrunde-Nordost",
        "NOFV-Pokal",
        "DFB-Nachwuchscup",
        "Verbandsliga Baden",
    ])
    def test_stichwort_in_staffel(self, staffel):
        assert sc._ist_fremder_verband(staffel) is True
        assert calculate_spesen("Kreisoberliga", "Herren", staffel) == LEER

    @pytest.mark.parametrize("staffel", [
        "", None, "Kreisliga Staffel 1", "Kreisoberliga Mittelthüringen",
        "Thüringenliga", "Landesklasse Staffel 2",
    ])
    def test_thueringer_staffel(self, staffel):
        assert sc._ist_fremder_verband(staffel) is False

    def test_thueringer_staffel_behaelt_satz(self):
        assert calculate_spesen("Kreisoberliga", "Herren", "Kreisoberliga Staffel 1") == (30.00, 25.00)

    @pytest.mark.parametrize("schluessel", [
        "FS/H/K-FS/MT/1", "FS/AJ/L-FS/TFV/1", "TU/H/VTUR/WT/1", "FS/H/K-FS/MTH/2",
        "FS/H/K-FS/NT/1", "FS/H/K-FS/OT/12", "FS/H/K-FS/E-S/1", "FS/H/K-FS/JSO/1",
        "TU/H/VTUR/NTKFA/3", "fs/h/k-fs/mt/1",
    ])
    def test_kurzschluessel_tfv(self, schluessel):
        assert sc._ist_fremder_verband(schluessel) is False

    @pytest.mark.parametrize("schluessel", [
        "FS/H/K-FS/SA/1", "TU/H/VTUR/BB/1", "FS/AJ/L-FS/SFV/1", "FS/H/K-FS/XX/99",
    ])
    def test_kurzschluessel_fremd(self, schluessel):
        assert sc._ist_fremder_verband(schluessel) is True

    @pytest.mark.parametrize("staffel", [
        # Kein Kurzschluessel im erwarteten Format -> Fliesstext, kein Stichwort
        "FS/H/K-FS/SA",          # Nummer fehlt
        "XX/H/K-FS/SA/1",        # falsches Praefix
        "FS/H/SA/1",             # zu wenige Felder
    ])
    def test_kein_gueltiger_kurzschluessel(self, staffel):
        assert sc._ist_fremder_verband(staffel) is False

    def test_fremder_kurzschluessel_leert_freundschaftsspiel(self, ligen):
        # Selbst ein bekannter Thueringer Gastgeber: fremder Verband geht vor
        assert calculate_spesen("Freundschaftsspiele", "Herren", "FS/H/K-FS/SA/1",
                                "FC Saalfeld", "Irgendwer") == LEER

    def test_fremder_verband_juniorinnen_leer(self):
        assert calculate_spesen("Landesliga", "B-Juniorinnen", "Landesliga Sachsen") == LEER


# ===== NOFV §9 Nr. 7 =====

class TestNofv:
    @pytest.mark.parametrize("mannschaftsart, schluessel, satz", [
        ("Herren", NOFV_HERREN_REGIONALLIGA, (300.00, 150.00)),
        ("Frauen", NOFV_FRAUEN_REGIONALLIGA, (60.00, 40.00)),
        ("A-Junioren", NOFV_A_JUNIOREN_REGIONALLIGA, (50.00, 35.00)),
        ("B-Junioren", NOFV_BC_JUNIOREN_REGIONALLIGA, (40.00, 30.00)),
        ("C-Junioren", NOFV_BC_JUNIOREN_REGIONALLIGA, (40.00, 30.00)),
        ("herren ", NOFV_HERREN_REGIONALLIGA, (300.00, 150.00)),
    ])
    def test_regionalliga(self, mannschaftsart, schluessel, satz):
        args = ("Regionalliga Nordost", mannschaftsart, "Regionalliga Nordost")
        assert nofv_spielklasse(*args) == schluessel
        assert calculate_spesen(*args) == satz
        assert SPESEN_NOFV[schluessel] == satz

    @pytest.mark.parametrize("staffel", [
        "NOFV-Oberliga Süd", "NOFV-Oberliga Nord", "nofv oberliga",
    ])
    def test_oberliga_herren(self, staffel):
        assert nofv_spielklasse("Oberliga", "Herren", staffel) == NOFV_HERREN_OBERLIGA
        assert calculate_spesen("Oberliga", "Herren", staffel) == (100.00, 60.00)

    @pytest.mark.parametrize("spielklasse, mannschaftsart, staffel", [
        # Oberliga eines anderen Regionalverbandes
        ("Oberliga", "Herren", "Oberliga Niedersachsen"),
        ("Oberliga", "Herren", "Bayernliga"),
        ("Oberliga", "Herren", ""),
        # "NOFV" ohne "Oberliga" in der Staffel
        ("Oberliga", "Herren", "NOFV-Staffel"),
        # Oberliga nur fuer Herren
        ("Oberliga", "Frauen", "NOFV-Oberliga Süd"),
        ("Oberliga", "A-Junioren", "NOFV-Oberliga Süd"),
        ("Oberliga", "Herren Ü35", "NOFV-Oberliga Süd"),
        # Spielklasse nicht exakt "Oberliga"
        ("Kreisoberliga", "Herren", "NOFV-Oberliga Süd"),
        # Regionalliga ohne "Nordost" in der Spielklasse
        ("Regionalliga", "Herren", "Regionalliga Nordost"),
        ("Regionalliga Nord", "Herren", "Regionalliga Nord"),
        # Regionalliga Nordost, aber Staffel nennt keine Regionalliga
        ("Regionalliga Nordost", "Herren", ""),
        ("Regionalliga Nordost", "Herren", "Staffel 1"),
        # Mannschaftsart nur exakt
        ("Regionalliga Nordost", "Herren Ü35", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "A-Juniorinnen", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "B-Juniorinnen", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "D-Junioren", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "Männer", "Regionalliga Nordost"),
        # Keine regulaeren Pflichtspiele
        ("Regionalliga Nordost", "C-Junioren", "Aufstiegsspiel zur NOFV-CJRL Regionalliga"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Relegation"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Entscheidungsspiel"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Qualifikation"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Turnier"),
        ("Regionalliga Nordost", "Herren", "Futsal-Regionalliga Nordost"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Halle"),
        ("Hallen-Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
        ("Oberliga", "Herren", "NOFV-Oberliga Süd Aufstieg"),
        # Pokal/Freundschaft sind keine Pflichtspiele mit festem Satz
        ("NOFV-Pokal Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
        ("Freundschaftsspiele Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
    ])
    def test_kein_nofv_pflichtspiel(self, spielklasse, mannschaftsart, staffel):
        assert nofv_spielklasse(spielklasse, mannschaftsart, staffel) is None
        # Und auch kein TFV-Satz: alles davon ist ueberregional oder fremd
        assert calculate_spesen(spielklasse, mannschaftsart, staffel) == LEER

    def test_nofv_none_eingaben(self):
        assert nofv_spielklasse(None, None, None) is None

    @pytest.mark.parametrize("spiel_info, erwartet", [
        ({"spielklasse": "Regionalliga Nordost", "mannschaftsart": "Herren",
          "staffel": "Regionalliga Nordost"}, True),
        ({"spielklasse": "Oberliga", "mannschaftsart": "Herren",
          "staffel": "NOFV-Oberliga Süd"}, True),
        ({"spielklasse": "Verbandsliga", "mannschaftsart": "Herren",
          "staffel": "Thüringenliga"}, False),
        ({"spielklasse": None, "mannschaftsart": None, "staffel": None}, False),
        ({}, False),
    ])
    def test_ist_nofv_spiel(self, spiel_info, erwartet):
        assert ist_nofv_spiel(spiel_info) is erwartet

    def test_nofv_vor_ueberregional_ausschluss(self):
        # "Regionalliga" waere sonst ueberregional und "Nordost" fremder Verband
        assert calculate_spesen("Regionalliga Nordost", "Frauen",
                                "Regionalliga Nordost") == (60.00, 40.00)


# ===== §2 Abs. 3/4 Pokal und Freundschaft - klassenunabhaengig =====

class TestPokalFreundschaftKlassenunabhaengig:
    @pytest.mark.parametrize("spielklasse", [
        "Kreispokal", "Landespokal", "Kreisfreundschaftsspiele", "Freundschaftsspiele",
    ])
    @pytest.mark.parametrize("mannschaftsart", ["A-Juniorinnen", "D-Juniorinnen", "Mädchen"])
    def test_juniorinnen(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (20.00, None)

    @pytest.mark.parametrize("spielklasse", ["Kreispokal", "Kreisfreundschaftsspiele"])
    @pytest.mark.parametrize("mannschaftsart", ["Herren Ü35", "Herren Ü50", "Alte Herren"])
    def test_alte_herren_kreis(self, spielklasse, mannschaftsart):
        assert calculate_spesen(spielklasse, mannschaftsart) == (25.00, 23.00)

    @pytest.mark.parametrize("spielklasse", ["Kreispokal Kleinfeld", "Kreisfreundschaftsspiele Kleinfeld"])
    def test_alte_herren_kreis_kleinfeld(self, spielklasse):
        assert calculate_spesen(spielklasse, "Herren Ü40") == (20.00, None)

    @pytest.mark.parametrize("spielklasse", ["Landespokal", "Freundschaftsspiele"])
    def test_alte_herren_landesebene_leer(self, spielklasse):
        assert calculate_spesen(spielklasse, "Herren Ü35", "", "A", "B") == LEER

    @pytest.mark.parametrize("spielklasse", [
        "Kreispokal", "Landespokal", "Kreisfreundschaftsspiele", "Freundschaftsspiele",
    ])
    @pytest.mark.parametrize("mannschaftsart", [
        "Frauen", "A-Junioren", "B-Junioren", "C-Junioren", "D-Junioren", "E-Junioren",
    ])
    def test_frauen_und_junioren_leer(self, spielklasse, mannschaftsart):
        # Satz haengt von der Spielklasse der Vereine ab, die nicht vorliegt
        assert calculate_spesen(spielklasse, mannschaftsart, "", "A", "B") == LEER

    @pytest.mark.parametrize("spielklasse", ["Kreispokal", "Kreisfreundschaftsspiele"])
    def test_kein_satz_der_punktspieltabelle(self, spielklasse):
        # Frueher bekamen Pokalspiele den Punktspielsatz der "kreis"-Zeile
        assert calculate_spesen(spielklasse, "Herren") == LEER
        assert calculate_spesen(spielklasse, "A-Junioren") == LEER
        assert calculate_spesen(spielklasse, "Frauen") == LEER


# ===== §2 Abs. 3/4 Herren nach Ligatabellen =====

class TestHerrenPokal:
    def test_kreispokal_nie(self, ligen):
        # Selbst mit Verbandsliga-Beteiligung: Kreispokal bleibt leer
        assert calculate_spesen("Kreispokal", "Herren", "", "FC Saalfeld", "SV 09 Arnstadt") == LEER

    @pytest.mark.parametrize("heim, gast, erwartet", [
        ("FC Saalfeld", "SV 09 Arnstadt", (50.00, 40.00)),          # VL vs VL
        ("FC Saalfeld", "FC Empor Weimar 06", (50.00, 40.00)),      # VL vs LK -> hoehere
        ("FC Empor Weimar 06", "FC Saalfeld", (50.00, 40.00)),      # Reihenfolge egal
        ("FC Empor Weimar 06", "SV Germania Ilmenau", (40.00, 30.00)),  # LK vs LK
        ("FC Empor Weimar 06", "SV Kreisklassenverein", (40.00, 30.00)),  # LK vs unbekannt
        ("SV Kreisklassenverein", "FC Saalfeld", (50.00, 40.00)),   # unbekannt vs VL
        ("SG FC Saalfeld", "Unbekannt", (50.00, 40.00)),            # SG-Praefix ignoriert
        ("FC Saalfeld I", "Unbekannt", (50.00, 40.00)),             # roemische Eins
    ])
    def test_landespokal(self, ligen, heim, gast, erwartet):
        assert calculate_spesen("Landespokal", "Herren", "", heim, gast) == erwartet

    @pytest.mark.parametrize("heim, gast", [
        ("FC Carl Zeiss Jena II", "FC Saalfeld"),   # Oberliga beteiligt
        ("FC Saalfeld", "FC Carl Zeiss Jena II"),
        ("FC Rot-Weiss Erfurt", "FC Empor Weimar 06"),  # Regionalliga beteiligt
        ("Unbekannt", "FC Rot-Weiss Erfurt"),
    ])
    def test_ueberregionale_beteiligung_leer(self, ligen, heim, gast):
        assert calculate_spesen("Landespokal", "Herren", "", heim, gast) == LEER

    def test_keiner_gefunden_leer(self, ligen):
        assert calculate_spesen("Landespokal", "Herren", "", "SV Niemand", "FC Keiner") == LEER

    @pytest.mark.parametrize("heim, gast", [("", "FC Saalfeld"), ("FC Saalfeld", ""), ("", "")])
    def test_pokal_braucht_beide_teams(self, ligen, heim, gast):
        assert calculate_spesen("Landespokal", "Herren", "", heim, gast) == LEER

    def test_ohne_teams_leer(self, ligen):
        assert calculate_spesen("Landespokal", "Herren") == LEER

    def test_mannschaftsnummer_entscheidet(self, ligen):
        # "FC Saalfeld 2." spielt Landesklasse, die Erste Verbandsliga
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld 2.", "Unbekannt") == (40.00, 30.00)
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld II", "Unbekannt") == (40.00, 30.00)

    def test_dritte_mannschaft_unbekannt(self, ligen):
        # "FC Saalfeld 3." steht nirgends - darf nicht die 50 der Ersten bekommen
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld 3.", "SV Niemand") == LEER

    def test_ohne_ueberregionale_tabellen_unbekannte_nicht_einzuordnen(self, ligen_ohne_ueberregional):
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld", "SV Unbekannt") == LEER

    def test_ohne_ueberregionale_tabellen_beide_bekannt(self, ligen_ohne_ueberregional):
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld",
                                "FC Empor Weimar 06") == (50.00, 40.00)

    def test_ohne_ligatabellen_leer(self, db):
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld", "SV 09 Arnstadt") == LEER

    def test_spielklasse_ohne_satz_leer(self, db):
        # Eine Landesliga (z.B. aus einem anderen Verband) hat keinen Herren-Satz
        _staffel("oberliga", "OL1", ["FC Ober"], verband="nofv")
        _staffel("landesliga", "LL1", ["SV Landesliga"])
        assert calculate_spesen("Landespokal", "Herren", "", "SV Landesliga", "Unbekannt") == LEER

    def test_mehrdeutige_mannschaft_alleine_leer(self, ligen):
        # Derselbe Kern in zwei Staffeln -> finde_mannschaft sagt None
        _staffel("landesklasse", "LK2", ["SV 09 Arnstadt"])
        assert calculate_spesen("Landespokal", "Herren", "", "SV 09 Arnstadt", "SV Niemand") == LEER

    def test_mehrdeutiger_gastgeber_im_freundschaftsspiel_leer(self, ligen):
        _staffel("landesklasse", "LK2", ["SV 09 Arnstadt"])
        assert calculate_spesen("Freundschaftsspiele", "Herren", "",
                                "SV 09 Arnstadt", "FC Empor Weimar 06") == LEER

    def test_mehrdeutige_mannschaft_mit_bekanntem_gegner_leer(self, ligen):
        # "SV 09 Arnstadt" steht in Verbandsliga UND Landesklasse - welche Zeile
        # gilt, ist nicht zu entscheiden. Der Gegner spielt Landesklasse.
        # Leer - der Satz des Gegners (40/30) waere geraten, es koennte 50/40 sein.
        _staffel("landesklasse", "LK2", ["SV 09 Arnstadt"])
        assert calculate_spesen("Landespokal", "Herren", "",
                                "SV 09 Arnstadt", "FC Empor Weimar 06") == LEER


class TestHerrenFreundschaft:
    @pytest.mark.parametrize("spielklasse", ["Freundschaftsspiele", "Kreisfreundschaftsspiele"])
    @pytest.mark.parametrize("heim, gast, erwartet", [
        ("FC Saalfeld", "SV Niemand", (50.00, 40.00)),
        ("FC Empor Weimar 06", "FC Saalfeld", (40.00, 30.00)),   # Gastgeber zaehlt allein
        ("FC Empor Weimar 06", "FC Rot-Weiss Erfurt", (40.00, 30.00)),  # Gast egal
        ("FC Empor Weimar 06", "", (40.00, 30.00)),              # Gast nicht noetig
    ])
    def test_gastgeber_entscheidet(self, ligen, spielklasse, heim, gast, erwartet):
        assert calculate_spesen(spielklasse, "Herren", "", heim, gast) == erwartet

    @pytest.mark.parametrize("heim", [
        "SV Niemand",              # nicht gefunden
        "",                        # fehlt
        "FC Carl Zeiss Jena II",   # Oberliga
        "FC Rot-Weiss Erfurt",     # Regionalliga
    ])
    def test_leer(self, ligen, heim):
        assert calculate_spesen("Freundschaftsspiele", "Herren", "", heim, "FC Saalfeld") == LEER

    def test_ohne_ueberregionale_tabellen_bekannter_gastgeber(self, ligen_ohne_ueberregional):
        assert calculate_spesen("Freundschaftsspiele", "Herren", "",
                                "FC Empor Weimar 06", "X") == (40.00, 30.00)

    def test_tfv_kurzschluessel_behaelt_satz(self, ligen):
        assert calculate_spesen("Kreisfreundschaftsspiele", "Herren", "FS/H/K-FS/MT/1",
                                "FC Saalfeld", "X") == (50.00, 40.00)


# ===== Rueckgabewerte =====

class TestRueckgabe:
    @pytest.mark.parametrize("args", [
        ("Verbandsliga", "Herren"),
        ("Kreisliga", "B-Junioren"),
        ("Kreisoberliga", "Frauen"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
    ])
    def test_immer_tupel_aus_zwei(self, args):
        ergebnis = calculate_spesen(*args)
        assert isinstance(ergebnis, tuple) and len(ergebnis) == 2
        assert isinstance(ergebnis[0], float)

    def test_sra_nie_ohne_sr(self):
        # Jede Tabellenzeile: wenn es einen SRA-Satz gibt, dann auch einen SR-Satz
        zeilen = [
            *sc.SPESEN_MAENNER.values(), *sc.SPESEN_FRAUEN.values(),
            *sc.SPESEN_NOFV.values(), *sc.SPESEN_HERREN_NACH_SPIELKLASSE.values(),
            sc.SPESEN_ALTE_HERREN_LANDESMEISTERSCHAFT, sc.SPESEN_ALTE_HERREN_KREIS,
            sc.SPESEN_ALTE_HERREN_KLEINFELD, sc.SPESEN_JUNIORINNEN_DEFAULT,
            sc.SPESEN_JUNIOREN_LANDESEBENE, sc.SPESEN_JUNIOREN_LANDESEBENE_DJUN,
            sc.SPESEN_JUNIOREN_KREISEBENE_AB, sc.SPESEN_JUNIOREN_KREISEBENE_JUNG,
        ]
        for sr, sra in zeilen:
            assert sr is not None and sr > 0
            assert sra is None or 0 < sra <= sr

    def test_tabellen_nicht_versehentlich_geaendert(self):
        # Festschreibung der Saetze laut Spesenordnung Stand 01.07.2025
        assert sc.SPESEN_MAENNER == {
            "verbandsliga": (50.00, 40.00),
            "landesklasse": (40.00, 30.00),
            "kreisoberliga": (30.00, 25.00),
            "kreisliga": (25.00, 23.00),
            "kreisklasse": (25.00, 23.00),
        }
        assert sc.SPESEN_FRAUEN == {
            "verbandsliga": (25.00, 20.00),
            "landesklasse": (25.00, 20.00),
            "kreisoberliga": (20.00, None),
        }
        assert sc.SPESEN_HERREN_NACH_SPIELKLASSE == {
            "verbandsliga": (50.00, 40.00),
            "landesklasse": (40.00, 30.00),
        }
        assert sc.SPESEN_NOFV == {
            NOFV_HERREN_REGIONALLIGA: (300.00, 150.00),
            NOFV_HERREN_OBERLIGA: (100.00, 60.00),
            NOFV_FRAUEN_REGIONALLIGA: (60.00, 40.00),
            NOFV_A_JUNIOREN_REGIONALLIGA: (50.00, 35.00),
            NOFV_BC_JUNIOREN_REGIONALLIGA: (40.00, 30.00),
        }


# ===== format_spesen =====

class TestFormat:
    @pytest.mark.parametrize("betrag, erwartet", [
        (25.0, "25,00 €"),
        (25, "25,00 €"),
        (23.5, "23,50 €"),
        (300.0, "300,00 €"),
        (0.0, "0,00 €"),
        (0, "0,00 €"),
        (1234.56, "1234,56 €"),
        (19.999, "20,00 €"),
        (None, ""),
    ])
    def test_format(self, betrag, erwartet):
        assert format_spesen(betrag) == erwartet

    def test_format_jedes_tabellenergebnis(self):
        sr, sra = calculate_spesen("Kreisliga", "Herren")
        assert (format_spesen(sr), format_spesen(sra)) == ("25,00 €", "23,00 €")
        sr, sra = calculate_spesen("Kreisoberliga", "Frauen")
        assert (format_spesen(sr), format_spesen(sra)) == ("20,00 €", "")
