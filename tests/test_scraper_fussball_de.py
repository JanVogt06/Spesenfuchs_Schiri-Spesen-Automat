"""
fussball.de: name comparison, division search and tables - without network.

Every retrieval goes through fussball_de._hole. The tests replace it with a
mapping URL -> HTML from tests/fixtures/scraper; a real retrieval (urlopen)
fails immediately.
"""
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from scraper import fussball_de
from scraper.fussball_de import (
    FussballDeNichtErreichbar,
    Staffel,
    Tabellenplatz,
    entdecke_staffeln,
    hole_tabelle,
    mannschaftsnummer,
    vereinskern,
)

FIXTURES = Path(__file__).parent / "fixtures" / "scraper"

SUCHE_URL = "https://www.fussball.de/suche/-/text/"
VEREIN_URL = (
    "https://www.fussball.de/verein/sv-gruen-weiss-beispielstadt-thueringen"
    "/-/id/00ES8GNBEISPIEL0VV0AG08LVUPGND5I"
)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _kein_netz(monkeypatch):
    """A real retrieval would be an error in the test."""
    def verboten(*args, **kwargs):
        raise AssertionError("Test wollte fussball.de wirklich abrufen")

    monkeypatch.setattr(fussball_de, "urlopen", verboten)


class FakeWeb:
    """Replaces _hole: URL -> HTML or exception; remembers every retrieval."""

    def __init__(self, seiten):
        self.seiten = dict(seiten)
        self.abrufe = []

    def __call__(self, url):
        self.abrufe.append(url)
        if url not in self.seiten:
            raise AssertionError(f"Unerwarteter Abruf: {url}")
        inhalt = self.seiten[url]
        if isinstance(inhalt, Exception):
            raise inhalt
        return inhalt


@pytest.fixture
def web(monkeypatch):
    def einrichten(seiten):
        fake = FakeWeb(seiten)
        monkeypatch.setattr(fussball_de, "_hole", fake)
        return fake

    return einrichten


def _staffel(staffel_id="02TESTVL00000000VS5489B3VVETK79U-G",
             slug="11teamsports-thueringenliga-verbandsliga-herren-saison2627-thueringen",
             anzeigename="11Teamsports Thüringenliga", spielklasse="verbandsliga"):
    return Staffel(
        staffel_id=staffel_id,
        pfad=f"/spieltagsuebersicht/{slug}/-/staffel/{staffel_id}",
        slug=slug,
        spielklasse=spielklasse,
        verband="thueringen",
        anzeigename=anzeigename,
    )


# ===== Team number =====

class TestMannschaftsnummer:
    @pytest.mark.parametrize("name, nummer", [
        ("FC Beispielstadt", 1),
        ("SG SV Musterdorf I", 1),
        ("FC Union Beispielstadt II", 2),
        ("FC Union Beispielstadt III", 3),
        ("FC Union Beispielstadt IV", 4),
        ("SV 09 Musterdorf 2.", 2),
        ("FC Empor Probehausen 06 2.", 2),
        ("SV Musterdorf 3", 3),
        ("SV Musterdorf 2 .", 2),
        ("  SV Musterdorf II  ", 2),
        ("sv musterdorf ii", 2),
    ])
    def test_erkennt_nummer(self, name, nummer):
        assert mannschaftsnummer(name) == nummer

    @pytest.mark.parametrize("name", [
        "SV 1920 Musterdorf",
        "SG Beispielstadt 46",
        "SpVgg Probehausen 04",
        "FC Hawaii",       # ends in "ii", but as part of a word
        "1. FC Beispielstadt",
    ])
    def test_jahreszahlen_und_woerter_sind_keine_nummer(self, name):
        assert mannschaftsnummer(name) == 1

    @pytest.mark.parametrize("name", ["", None])
    def test_leer_ist_erste_mannschaft(self, name):
        assert mannschaftsnummer(name) == 1


# ===== Club core =====

class TestVereinskern:
    def test_spielgemeinschaft_und_nummer_fallen_weg(self):
        assert vereinskern("SG SV Musterdorf I") == "sv musterdorf"
        assert vereinskern("SG SV Musterdorf I") == vereinskern("SV Musterdorf")

    def test_spg_und_mehrfache_kennzeichnung(self):
        assert vereinskern("SpG SG FC Probehausen") == "fc probehausen"

    def test_umlaute_und_scharfes_s(self):
        assert vereinskern("SV Grün-Weiß Beispielstadt") == "sv grun weiss beispielstadt"

    def test_zeichensetzung_und_unsichtbare_zeichen(self):
        assert vereinskern("BFC ­Beispiel​stadt") == "bfc beispielstadt"
        assert vereinskern("FC Beispielstadt/Nord e.V.") == "fc beispielstadt nord e v"

    def test_nummer_wird_getrennt_verglichen(self):
        assert vereinskern("SV 09 Musterdorf 2.") == "sv 09 musterdorf"
        assert vereinskern("FC Union Beispielstadt II") == "fc union beispielstadt"

    def test_zahlen_im_namen_bleiben(self):
        # Two different clubs of the same town must not collapse
        assert vereinskern("SV 09 Musterdorf") != vereinskern("SV 1920 Musterdorf")
        assert vereinskern("SG Beispielstadt 46") != vereinskern("FC Beispielstadt")

    def test_rechtsform_bleibt_stehen(self):
        assert vereinskern("SG Beispielstadt 46") == "beispielstadt 46"
        assert vereinskern("FC Beispielstadt") == "fc beispielstadt"

    @pytest.mark.parametrize("name", ["", None, "SG", "  "])
    def test_leer(self, name):
        assert vereinskern(name) == ""


# ===== Divisions on a page =====

class TestStaffelnAufSeite:
    def test_verbandsliga_herren_thueringen(self):
        staffeln = fussball_de._staffeln_auf_seite(
            _fixture("fussballde_verein.html"), "verbandsliga", "thueringen"
        )

        assert staffeln == [_staffel()]
        assert staffeln[0].url == (
            "https://www.fussball.de/spieltagsuebersicht/11teamsports-thueringenliga-"
            "verbandsliga-herren-saison2627-thueringen/-/staffel/02TESTVL00000000VS5489B3VVETK79U-G"
        )

    def test_junioren_frauen_und_fremder_verband_fallen_weg(self):
        html = _fixture("fussballde_verein.html")

        sachsen_anhalt = fussball_de._staffeln_auf_seite(html, "verbandsliga", "sachsen-anhalt")
        assert [s.staffel_id for s in sachsen_anhalt] == ["02TESTSAVL000000VS5489B3VVETK79U-G"]

        alle_ids = {s.staffel_id for s in fussball_de._staffeln_auf_seite(html, "verbandsliga", "thueringen")}
        assert "02TESTAJVL000000VS5489B3VVETK79U-G" not in alle_ids
        assert "02TESTFRVL000000VS5489B3VVETK79U-G" not in alle_ids

    def test_spielklasse_mit_kreis_im_slug(self):
        staffeln = fussball_de._staffeln_auf_seite(
            _fixture("fussballde_verein.html"), "kreisoberliga", "thueringen"
        )
        assert [s.anzeigename for s in staffeln] == ["Kreisoberliga Mittelthüringen"]

    def test_verband_mit_bindestrich(self):
        staffeln = fussball_de._staffeln_auf_seite(
            _fixture("fussballde_verein.html"), "regionalliga", "region-nordostdeutschland"
        )
        assert [s.staffel_id for s in staffeln] == ["02TESTRLNO000000VS5489B3VVETK79U-G"]

    def test_nicht_gespielte_spielklasse(self):
        assert fussball_de._staffeln_auf_seite(
            _fixture("fussballde_verein.html"), "oberliga", "deutschland"
        ) == []

    def test_link_ohne_text_ergibt_slug_als_namen(self):
        html = ('<a href="/spieltagsuebersicht/landesklasse-staffel-1-landesklasse-herren-'
                'saison2627-thueringen/-/staffel/02TESTLK10000000VS5489B3VVETK79U-G">'
                '<span class="icon"></span></a>')
        staffel, = fussball_de._staffeln_auf_seite(html, "landesklasse", "thueringen")
        assert staffel.anzeigename == staffel.slug

    def test_anzeigename_ohne_tags_und_entities(self):
        html = ('<a href="/spieltagsuebersicht/x-verbandsliga-herren-saison2627-thueringen'
                '/-/staffel/02ABC" class="c"><b>Th&uuml;ringen</b>\n  liga</a>')
        assert fussball_de._anzeigename(html, "02ABC") == "Thüringen liga"
        assert fussball_de._anzeigename(html, "02XYZ") is None


# ===== Discovering divisions =====

LK = "https://www.fussball.de/spieltagsuebersicht/landesklasse-staffel-{n}-landesklasse-herren-saison2627-thueringen/-/staffel/02TESTLK{n}0000000VS5489B3VVETK79U-G"


def _landesklasse_seite(n, nachbarn, name=None):
    """A division page that points to its neighbours via rel=prev/next."""
    links = "\n".join(
        f'<a rel="{richtung}" href="{LK.format(n=nachbar)}"><span class="icon-arrow"></span></a>'
        for richtung, nachbar in nachbarn
    )
    favorit = ""
    if name:
        favorit = (f'<a href="https://www.fussball.de/my.add.favorite?type=staffel&text='
                   f'26%2F27+-+Herren+-+Landesklasse+-+Th%C3%BCringen%3A+{name.replace(" ", "+")}"></a>')
    return f"<html><body>{favorit}{links}</body></html>"


class TestEntdeckeStaffeln:
    def test_sucht_verein_ueber_textsuche(self, web):
        fake = web({
            SUCHE_URL + "SV%20Gr%C3%BCn-Wei%C3%9F%20Beispielstadt": _fixture("fussballde_suche.html"),
            VEREIN_URL: _fixture("fussballde_verein.html"),
        })

        staffeln = entdecke_staffeln("SV Grün-Weiß Beispielstadt", "verbandsliga",
                                     mit_nachbarstaffeln=False)

        assert staffeln == [_staffel()]
        # First search hit, and without neighbouring divisions no division page
        assert fake.abrufe == [SUCHE_URL + "SV%20Gr%C3%BCn-Wei%C3%9F%20Beispielstadt", VEREIN_URL]

    def test_kein_suchtreffer(self, web):
        fake = web({SUCHE_URL + "Niemand": "<html><body>Keine Treffer</body></html>"})

        assert entdecke_staffeln("Niemand", "verbandsliga") == []
        assert len(fake.abrufe) == 1

    def test_verein_spielt_nicht_in_der_liga(self, web):
        fake = web({
            SUCHE_URL + "Beispielstadt": _fixture("fussballde_suche.html"),
            VEREIN_URL: _fixture("fussballde_verein.html"),
        })

        assert entdecke_staffeln("Beispielstadt", "oberliga", "deutschland") == []
        assert len(fake.abrufe) == 2

    def test_suche_nicht_erreichbar_wird_weitergereicht(self, web):
        web({SUCHE_URL + "Beispielstadt": FussballDeNichtErreichbar("503")})

        with pytest.raises(FussballDeNichtErreichbar):
            entdecke_staffeln("Beispielstadt", "verbandsliga")

    def test_folgt_der_kette_in_beide_richtungen(self, web):
        # The anchor plays in the MIDDLE division: following only rel=next
        # would never have found division 1.
        fake = web({
            SUCHE_URL + "Beispielstadt": _fixture("fussballde_suche.html"),
            VEREIN_URL: _fixture("fussballde_verein.html"),
            LK.format(n=2): _landesklasse_seite(2, [("prev", 1), ("next", 3)], "Landesklasse Staffel 2"),
            LK.format(n=1): _landesklasse_seite(1, [("next", 2)], "Landesklasse Staffel 1"),
            LK.format(n=3): _landesklasse_seite(3, [("prev", 2)], "Landesklasse Staffel 3"),
        })

        staffeln = entdecke_staffeln("Beispielstadt", "landesklasse")

        assert [s.anzeigename for s in staffeln] == [
            "Landesklasse Staffel 1", "Landesklasse Staffel 2", "Landesklasse Staffel 3",
        ]
        assert [s.staffel_id for s in staffeln] == [
            "02TESTLK10000000VS5489B3VVETK79U-G",
            "02TESTLK20000000VS5489B3VVETK79U-G",
            "02TESTLK30000000VS5489B3VVETK79U-G",
        ]
        assert all(s.spielklasse == "landesklasse" and s.verband == "thueringen" for s in staffeln)
        # The chain closes: no division page is fetched endlessly again
        assert fake.abrufe.count(LK.format(n=2)) == 1

    def test_nachbar_nicht_erreichbar(self, web):
        web({
            SUCHE_URL + "Beispielstadt": _fixture("fussballde_suche.html"),
            VEREIN_URL: _fixture("fussballde_verein.html"),
            LK.format(n=2): _landesklasse_seite(2, [("next", 3)]),
            LK.format(n=3): FussballDeNichtErreichbar("Zeitueberschreitung"),
        })

        staffeln = entdecke_staffeln("Beispielstadt", "landesklasse")

        # Division 3 is known, but its name cannot be fetched: the slug remains
        assert {s.staffel_id: s.anzeigename for s in staffeln} == {
            "02TESTLK20000000VS5489B3VVETK79U-G": "Landesklasse Staffel 2",
            "02TESTLK30000000VS5489B3VVETK79U-G":
                "landesklasse-staffel-3-landesklasse-herren-saison2627-thueringen",
        }

    def test_kette_ignoriert_fremde_spielklassen(self, web):
        fremd = ("https://www.fussball.de/spieltagsuebersicht/kreisliga-kreisliga-herren-"
                 "saison2627-thueringen/-/staffel/02FREMD")
        web({
            SUCHE_URL + "Beispielstadt": _fixture("fussballde_suche.html"),
            VEREIN_URL: _fixture("fussballde_verein.html"),
            LK.format(n=2): f'<a rel="next" href="{fremd}"></a>',
        })

        staffeln = entdecke_staffeln("Beispielstadt", "landesklasse")

        assert [s.staffel_id for s in staffeln] == ["02TESTLK20000000VS5489B3VVETK79U-G"]


class TestMitAnzeigename:
    def test_staffel_mit_namen_wird_nicht_abgerufen(self, web):
        fake = web({})
        staffel = _staffel()
        assert fussball_de._mit_anzeigename(staffel) is staffel
        assert fake.abrufe == []

    def test_name_aus_favoritenlink(self, web):
        staffel = _staffel(anzeigename="11teamsports-thueringenliga-verbandsliga-herren-saison2627-thueringen")
        web({staffel.url: _fixture("fussballde_tabelle.html")})

        assert fussball_de._mit_anzeigename(staffel).anzeigename == "11Teamsports Thüringenliga"

    @pytest.mark.parametrize("href", [
        "my.add.favorite?text=26%2F27+-+Herren+-+Landesklasse+-+Th%C3%BCringen%3A+Landesklasse+Staffel+1&amp;type=staffel",
        "my.add.favorite?type=staffel&amp;text=26%2F27+-+Herren+-+Landesklasse+-+Th%C3%BCringen%3A+Landesklasse+Staffel+1",
        "my.add.favorite?type=staffel&text=26%2F27+-+Herren+-+Landesklasse+-+Th%C3%BCringen%3A+Landesklasse+Staffel+1",
    ])
    def test_name_aus_jeder_linkform(self, web, href):
        staffel = _staffel(anzeigename=_staffel().slug)
        web({staffel.url: f'<a href="https://www.fussball.de/{href}" class="icon-star"></a>'})

        assert fussball_de._mit_anzeigename(staffel).anzeigename == "Landesklasse Staffel 1"

    def test_ohne_favoritenlink_bleibt_slug(self, web):
        staffel = _staffel(anzeigename=_staffel().slug)
        web({staffel.url: "<html></html>"})

        assert fussball_de._mit_anzeigename(staffel) == staffel


# ===== Table =====

class TestHoleTabelle:
    def test_liest_tabelle(self, web):
        staffel = _staffel()
        web({staffel.url: _fixture("fussballde_tabelle.html")})

        tabelle = hole_tabelle(staffel)

        assert tabelle == [
            Tabellenplatz(platz=1, mannschaft="FC Beispielstadt",
                          team_id="011MITEAM0001000VTVG0001VTR8C1K7",
                          spiele=12, siege=9, unentschieden=2, niederlagen=1,
                          tore=31, gegentore=9, punkte=29),
            Tabellenplatz(platz=2, mannschaft="SV Grün-Weiß Musterdorf 2.",
                          team_id="011MITEAM0002000VTVG0001VTR8C1K7",
                          spiele=12, siege=7, unentschieden=3, niederlagen=2,
                          tore=20, gegentore=14, punkte=24),
            Tabellenplatz(platz=3, mannschaft="SG Probehausen",
                          team_id="011MITEAM0003000VTVG0001VTR8C1K7",
                          spiele=12, siege=0, unentschieden=1, niederlagen=11,
                          tore=4, gegentore=40, punkte=1),
        ]

    def test_seite_ohne_tabelle(self, web):
        staffel = _staffel()
        web({staffel.url: "<html><body>Pokalrunde</body></html>"})

        assert hole_tabelle(staffel) == []

    def test_nicht_erreichbar_wird_weitergereicht(self, web):
        staffel = _staffel()
        web({staffel.url: FussballDeNichtErreichbar("500")})

        with pytest.raises(FussballDeNichtErreichbar):
            hole_tabelle(staffel)


class TestZeileAuswerten:
    ZEILE = ('<td class="column-rank">{rang}</td>'
             '<td class="column-club"><a href="/mannschaft/x/-/saison/2627/team-id/011ABC">FC X</a></td>'
             '<td>10</td><td>5</td><td>3</td><td>2</td><td>{tore}</td>'
             '<td class="column-points">{punkte}</td>')

    def test_vollstaendige_zeile(self):
        platz = fussball_de._zeile_auswerten(self.ZEILE.format(rang="7.", tore="12 : 10", punkte="18"))
        assert platz == Tabellenplatz(7, "FC X", "011ABC", 10, 5, 3, 2, 12, 10, 18)

    @pytest.mark.parametrize("rang, tore, punkte", [
        ("", "12 : 10", "18"),      # no rank
        ("7.", "12 : 10", ""),      # no points
        ("7.", "", "18"),           # no goal difference
        ("x", "12 : 10", "18"),     # rank not a number
        ("7.", "12 : 10", "n.a."),  # points not a number
    ])
    def test_halbe_zeile_wird_verworfen(self, rang, tore, punkte):
        assert fussball_de._zeile_auswerten(self.ZEILE.format(rang=rang, tore=tore, punkte=punkte)) is None

    def test_zu_wenige_zahlen(self):
        zeile = ('<td class="column-rank">1.</td>'
                 '<td class="column-club"><a href="/mannschaft/x/-/team-id/011ABC">FC X</a></td>'
                 '<td>10</td><td>5</td><td>1 : 0</td><td class="column-points">3</td>')
        assert fussball_de._zeile_auswerten(zeile) is None

    def test_kopfzeile(self):
        assert fussball_de._zeile_auswerten("<th>Pl.</th><th>Mannschaft</th>") is None


# ===== Retrieval =====

class FakeAntwort:
    def __init__(self, inhalt: bytes):
        self.inhalt = inhalt

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.inhalt


class FakeZeit:
    def __init__(self, jetzt=1000.0):
        self.jetzt = jetzt
        self.pausen = []

    def monotonic(self):
        return self.jetzt

    def sleep(self, sekunden):
        self.pausen.append(sekunden)
        self.jetzt += sekunden


class TestHole:
    @pytest.fixture
    def zeit(self, monkeypatch):
        zeit = FakeZeit()
        monkeypatch.setattr(fussball_de, "time", SimpleNamespace(monotonic=zeit.monotonic, sleep=zeit.sleep))
        monkeypatch.setattr(fussball_de, "_letzte_anfrage", 0.0)
        return zeit

    def test_liefert_text_und_sendet_user_agent(self, monkeypatch, zeit):
        anfragen = []

        def fake_urlopen(anfrage, timeout):
            anfragen.append((anfrage, timeout))
            return FakeAntwort("Thüringen".encode("utf-8"))

        monkeypatch.setattr(fussball_de, "urlopen", fake_urlopen)

        assert fussball_de._hole("https://www.fussball.de/x") == "Thüringen"

        anfrage, timeout = anfragen[0]
        assert anfrage.full_url == "https://www.fussball.de/x"
        assert anfrage.get_method() == "GET"
        assert anfrage.get_header("User-agent").startswith("Spesenfuchs/")
        assert timeout == fussball_de.TIMEOUT_SEKUNDEN
        assert zeit.pausen == []

    def test_kaputtes_utf8_wird_ersetzt(self, monkeypatch, zeit):
        monkeypatch.setattr(fussball_de, "urlopen", lambda anfrage, timeout: FakeAntwort(b"a\xffb"))
        assert fussball_de._hole("https://www.fussball.de/x") == "a�b"

    def test_haelt_mindestabstand(self, monkeypatch, zeit):
        monkeypatch.setattr(fussball_de, "urlopen", lambda anfrage, timeout: FakeAntwort(b""))

        fussball_de._hole("https://www.fussball.de/a")
        zeit.jetzt += 0.25
        fussball_de._hole("https://www.fussball.de/b")

        assert zeit.pausen == [pytest.approx(0.75)]

    @pytest.mark.parametrize("fehler", [
        URLError("kein DNS"),
        HTTPError("https://www.fussball.de/x", 503, "Service Unavailable", {}, None),
        TimeoutError("zu langsam"),
        ConnectionResetError("abgebrochen"),
    ])
    def test_fehler_werden_zu_nicht_erreichbar(self, monkeypatch, zeit, fehler):
        def fake_urlopen(anfrage, timeout):
            raise fehler

        monkeypatch.setattr(fussball_de, "urlopen", fake_urlopen)

        with pytest.raises(FussballDeNichtErreichbar, match="https://www.fussball.de/x"):
            fussball_de._hole("https://www.fussball.de/x")

        # A failure also counts towards the minimum interval
        assert fussball_de._letzte_anfrage == zeit.jetzt
