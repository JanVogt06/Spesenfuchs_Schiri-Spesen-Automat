"""
Expense calculator according to TFV expense regulations §2 and NOFV finance
regulations §9 no. 7.

Money-critical. The app's guideline: where the rate is not clearly
established, the result is (None, None) - never a guessed amount. These
cases are explicitly covered here.
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


# ===== League tables for cup/friendly =====

def _staffel(spielklasse, staffel_id, mannschaften, verband="thueringen"):
    """Creates a division including table via the real write path."""
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
    Thuringian state level plus supra-regional tables:
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
    """Thuringian state level only - the supra-regional tables are missing."""
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
        # Cup takes precedence if both words occur
        ("Pokal-Freundschaftsturnier", POKALSPIEL),
    ])
    def test_zuordnung(self, spielklasse, erwartet):
        assert wettbewerbsart(spielklasse) == erwartet


# ===== Input validation =====

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


# ===== §2 Abs. 2a Men =====

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
        # Case does not matter
        ("VERBANDSLIGA", (50.00, 40.00)),
        ("kreisoberliga", (30.00, 25.00)),
        # District fallback: everything with "kreis" without a table row
        ("Kreismeisterschaft", (25.00, 23.00)),
        ("Hallenkreismeisterschaft", (25.00, 23.00)),
    ])
    def test_tabelle(self, spielklasse, erwartet):
        assert calculate_spesen(spielklasse, "Herren") == erwartet

    @pytest.mark.parametrize("mannschaftsart", ["Herren", "Männer", "HERREN", "herren"])
    def test_schreibweisen_der_mannschaftsart(self, mannschaftsart):
        assert calculate_spesen("Verbandsliga", mannschaftsart) == (50.00, 40.00)

    def test_kreisoberliga_nicht_als_kreisliga(self):
        # "kreisoberliga" contains "kreis" and "liga" - must not become 25/23
        assert calculate_spesen("Kreisoberliga", "Herren") == (30.00, 25.00)

    def test_kreisoberliga_nicht_als_oberliga_ueberregional(self):
        # "Kreisoberliga" contains "oberliga" - but is district level
        assert calculate_spesen("Kreisoberliga", "Herren") != LEER

    @pytest.mark.parametrize("spielklasse", [
        "Landesliga",          # does not exist for TFV men
        "Landesturnier",       # Men's tournament at state level: no row
        "Stadtliga",
        "Thüringenliga",       # Sponsor name without "verbandsliga"
        "  ",
    ])
    def test_unbekannte_landesklasse_leer(self, spielklasse):
        assert calculate_spesen(spielklasse, "Herren") == LEER


# ===== §2 Abs. 2a Alte Herren (veterans) =====

class TestAlteHerren:
    @pytest.mark.parametrize("mannschaftsart", [
        "Herren Ü32", "Herren Ü35", "Herren Ü40", "Herren Ü45", "Herren Ü50",
        "Herren Ü 40", "Alte Herren",
    ])
    @pytest.mark.parametrize("spielklasse", ["Kreisoberliga", "Kreisliga", "Kreisklasse"])
    def test_kreis_einheitlich(self, spielklasse, mannschaftsart):
        # Kreisoberliga Ue45 must NOT get the 30/25 of the men
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
        # No men's table for veterans - better empty
        assert calculate_spesen(spielklasse, "Herren Ü40") == LEER

    @pytest.mark.parametrize("mannschaftsart, erwartet", [
        ("herren ü32", True),
        ("herren ü 35", True),
        ("herren ü50", True),
        ("alte herren", True),
        ("herren", False),
        ("männer", False),
        ("herren ü3", False),    # single-digit is not an age group
        ("a-junioren", False),
    ])
    def test_is_alte_herren(self, mannschaftsart, erwartet):
        # Callers pass the team type in lower case
        assert bool(is_alte_herren(mannschaftsart)) is erwartet


# ===== §2 Abs. 2b Women/junior girls =====

class TestFrauen:
    @pytest.mark.parametrize("spielklasse, erwartet", [
        ("Verbandsliga", (25.00, 20.00)),
        ("Landesklasse", (25.00, 20.00)),
        ("Kreisoberliga", (20.00, None)),
        ("Kreisliga", (20.00, None)),       # District fallback
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


# ===== §2 Abs. 2c Juniors =====

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
        # Closed list: do not silently bill foreign state associations at 25/20
        assert calculate_spesen(spielklasse, "B-Junioren") == LEER

    @pytest.mark.parametrize("spielklasse", [
        "A-Junioren-Bundesliga", "B-Junioren-Bundesliga", "Nachwuchsliga",
        "Regionalliga", "Oberliga", "DFB-Nachwuchsliga",
    ])
    def test_ueberregional_leer(self, spielklasse):
        assert calculate_spesen(spielklasse, "A-Junioren") == LEER


# ===== Supra-regional =====

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


# ===== §2 Abs. 6 foreign associations =====

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
        # No short key in the expected format -> free text, no keyword
        "FS/H/K-FS/SA",          # number missing
        "XX/H/K-FS/SA/1",        # wrong prefix
        "FS/H/SA/1",             # too few fields
    ])
    def test_kein_gueltiger_kurzschluessel(self, staffel):
        assert sc._ist_fremder_verband(staffel) is False

    def test_fremder_kurzschluessel_leert_freundschaftsspiel(self, ligen):
        # Even a known Thuringian host: foreign association takes precedence
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
        # Oberliga of a different regional association
        ("Oberliga", "Herren", "Oberliga Niedersachsen"),
        ("Oberliga", "Herren", "Bayernliga"),
        ("Oberliga", "Herren", ""),
        # "NOFV" without "Oberliga" in the division
        ("Oberliga", "Herren", "NOFV-Staffel"),
        # Oberliga only for men
        ("Oberliga", "Frauen", "NOFV-Oberliga Süd"),
        ("Oberliga", "A-Junioren", "NOFV-Oberliga Süd"),
        ("Oberliga", "Herren Ü35", "NOFV-Oberliga Süd"),
        # League class not exactly "Oberliga"
        ("Kreisoberliga", "Herren", "NOFV-Oberliga Süd"),
        # Regionalliga without "Nordost" in the league class
        ("Regionalliga", "Herren", "Regionalliga Nordost"),
        ("Regionalliga Nord", "Herren", "Regionalliga Nord"),
        # Regionalliga Nordost, but the division names no Regionalliga
        ("Regionalliga Nordost", "Herren", ""),
        ("Regionalliga Nordost", "Herren", "Staffel 1"),
        # Team type exact only
        ("Regionalliga Nordost", "Herren Ü35", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "A-Juniorinnen", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "B-Juniorinnen", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "D-Junioren", "Regionalliga Nordost"),
        ("Regionalliga Nordost", "Männer", "Regionalliga Nordost"),
        # No regular compulsory matches
        ("Regionalliga Nordost", "C-Junioren", "Aufstiegsspiel zur NOFV-CJRL Regionalliga"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Relegation"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Entscheidungsspiel"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Qualifikation"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Turnier"),
        ("Regionalliga Nordost", "Herren", "Futsal-Regionalliga Nordost"),
        ("Regionalliga Nordost", "Herren", "Regionalliga Nordost Halle"),
        ("Hallen-Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
        ("Oberliga", "Herren", "NOFV-Oberliga Süd Aufstieg"),
        # Cup/friendly are not compulsory matches with a fixed rate
        ("NOFV-Pokal Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
        ("Freundschaftsspiele Regionalliga Nordost", "Herren", "Regionalliga Nordost"),
    ])
    def test_kein_nofv_pflichtspiel(self, spielklasse, mannschaftsart, staffel):
        assert nofv_spielklasse(spielklasse, mannschaftsart, staffel) is None
        # And no TFV rate either: all of it is supra-regional or foreign
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
        # "Regionalliga" would otherwise be supra-regional and "Nordost" a foreign association
        assert calculate_spesen("Regionalliga Nordost", "Frauen",
                                "Regionalliga Nordost") == (60.00, 40.00)


# ===== §2 Abs. 3/4 Cup and friendly - independent of class =====

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
        # Rate depends on the league class of the clubs, which is not available
        assert calculate_spesen(spielklasse, mannschaftsart, "", "A", "B") == LEER

    @pytest.mark.parametrize("spielklasse", ["Kreispokal", "Kreisfreundschaftsspiele"])
    def test_kein_satz_der_punktspieltabelle(self, spielklasse):
        # Previously, cup matches got the league-match rate of the "kreis" row
        assert calculate_spesen(spielklasse, "Herren") == LEER
        assert calculate_spesen(spielklasse, "A-Junioren") == LEER
        assert calculate_spesen(spielklasse, "Frauen") == LEER


# ===== §2 Abs. 3/4 Men by league tables =====

class TestHerrenPokal:
    def test_kreispokal_nie(self, ligen):
        # Even with Verbandsliga participation: district cup stays empty
        assert calculate_spesen("Kreispokal", "Herren", "", "FC Saalfeld", "SV 09 Arnstadt") == LEER

    @pytest.mark.parametrize("heim, gast, erwartet", [
        ("FC Saalfeld", "SV 09 Arnstadt", (50.00, 40.00)),          # VL vs VL
        ("FC Saalfeld", "FC Empor Weimar 06", (50.00, 40.00)),      # VL vs LK -> higher
        ("FC Empor Weimar 06", "FC Saalfeld", (50.00, 40.00)),      # Order does not matter
        ("FC Empor Weimar 06", "SV Germania Ilmenau", (40.00, 30.00)),  # LK vs LK
        ("FC Empor Weimar 06", "SV Kreisklassenverein", (40.00, 30.00)),  # LK vs unknown
        ("SV Kreisklassenverein", "FC Saalfeld", (50.00, 40.00)),   # unknown vs VL
        ("SG FC Saalfeld", "Unbekannt", (50.00, 40.00)),            # SG prefix ignored
        ("FC Saalfeld I", "Unbekannt", (50.00, 40.00)),             # Roman one
    ])
    def test_landespokal(self, ligen, heim, gast, erwartet):
        assert calculate_spesen("Landespokal", "Herren", "", heim, gast) == erwartet

    @pytest.mark.parametrize("heim, gast", [
        ("FC Carl Zeiss Jena II", "FC Saalfeld"),   # Oberliga involved
        ("FC Saalfeld", "FC Carl Zeiss Jena II"),
        ("FC Rot-Weiss Erfurt", "FC Empor Weimar 06"),  # Regionalliga involved
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
        # "FC Saalfeld 2." plays Landesklasse, the first team Verbandsliga
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld 2.", "Unbekannt") == (40.00, 30.00)
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld II", "Unbekannt") == (40.00, 30.00)

    def test_dritte_mannschaft_unbekannt(self, ligen):
        # "FC Saalfeld 3." is nowhere - must not get the first team's 50
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld 3.", "SV Niemand") == LEER

    def test_ohne_ueberregionale_tabellen_unbekannte_nicht_einzuordnen(self, ligen_ohne_ueberregional):
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld", "SV Unbekannt") == LEER

    def test_ohne_ueberregionale_tabellen_beide_bekannt(self, ligen_ohne_ueberregional):
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld",
                                "FC Empor Weimar 06") == (50.00, 40.00)

    def test_ohne_ligatabellen_leer(self, db):
        assert calculate_spesen("Landespokal", "Herren", "", "FC Saalfeld", "SV 09 Arnstadt") == LEER

    def test_spielklasse_ohne_satz_leer(self, db):
        # A Landesliga (e.g. from another association) has no men's rate
        _staffel("oberliga", "OL1", ["FC Ober"], verband="nofv")
        _staffel("landesliga", "LL1", ["SV Landesliga"])
        assert calculate_spesen("Landespokal", "Herren", "", "SV Landesliga", "Unbekannt") == LEER

    def test_mehrdeutige_mannschaft_alleine_leer(self, ligen):
        # The same core in two divisions -> finde_mannschaft says None
        _staffel("landesklasse", "LK2", ["SV 09 Arnstadt"])
        assert calculate_spesen("Landespokal", "Herren", "", "SV 09 Arnstadt", "SV Niemand") == LEER

    def test_mehrdeutiger_gastgeber_im_freundschaftsspiel_leer(self, ligen):
        _staffel("landesklasse", "LK2", ["SV 09 Arnstadt"])
        assert calculate_spesen("Freundschaftsspiele", "Herren", "",
                                "SV 09 Arnstadt", "FC Empor Weimar 06") == LEER

    def test_mehrdeutige_mannschaft_mit_bekanntem_gegner_leer(self, ligen):
        # "SV 09 Arnstadt" is in Verbandsliga AND Landesklasse - which row
        # applies cannot be decided. The opponent plays Landesklasse.
        # Empty - the opponent's rate (40/30) would be a guess, it could be 50/40.
        _staffel("landesklasse", "LK2", ["SV 09 Arnstadt"])
        assert calculate_spesen("Landespokal", "Herren", "",
                                "SV 09 Arnstadt", "FC Empor Weimar 06") == LEER


class TestHerrenFreundschaft:
    @pytest.mark.parametrize("spielklasse", ["Freundschaftsspiele", "Kreisfreundschaftsspiele"])
    @pytest.mark.parametrize("heim, gast, erwartet", [
        ("FC Saalfeld", "SV Niemand", (50.00, 40.00)),
        ("FC Empor Weimar 06", "FC Saalfeld", (40.00, 30.00)),   # Host counts alone
        ("FC Empor Weimar 06", "FC Rot-Weiss Erfurt", (40.00, 30.00)),  # Guest irrelevant
        ("FC Empor Weimar 06", "", (40.00, 30.00)),              # Guest not needed
    ])
    def test_gastgeber_entscheidet(self, ligen, spielklasse, heim, gast, erwartet):
        assert calculate_spesen(spielklasse, "Herren", "", heim, gast) == erwartet

    @pytest.mark.parametrize("heim", [
        "SV Niemand",              # not found
        "",                        # missing
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


# ===== Return values =====

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
        # Every table row: if there is an SRA rate, there is also an SR rate
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
        # Fixing of the rates according to the expense regulations as of 01.07.2025
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
