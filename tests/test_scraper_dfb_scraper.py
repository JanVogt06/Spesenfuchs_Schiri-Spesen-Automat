"""
DFBScraper ohne Browser.

Statt Playwright bekommt der Scraper eine Seite aus Attrappen: Loc steht fuer
einen Locator und kennt nur die Selektoren, die ihm ein Test mitgibt. Jeder
andere Selektor liefert einen unsichtbaren Locator, dessen wait_for in einen
Timeout laeuft - so wie eine Seite, auf der das Element nie erscheint.

Die Wartelogik laeuft gegen eine Uhr, die nur page.wait_for_timeout vorstellt.
Damit lassen sich dfb-spinner, "erst Kopfzeilen, dann Daten" und Timeouts
durchspielen, ohne dass ein Test wirklich wartet.
"""
from types import SimpleNamespace

import pytest

from core.errors import DFBCredentialsInvalidError
from scraper import dfb_scraper, spielberichte
from scraper.dfb_scraper import DFBScraper


@pytest.fixture(autouse=True)
def _kein_browser(monkeypatch):
    def verboten(*args, **kwargs):
        raise AssertionError("Test wollte einen echten Browser starten")

    monkeypatch.setattr(dfb_scraper, "sync_playwright", verboten)


# ===== Attrappen =====

class PlaywrightTimeout(Exception):
    pass


class Loc:
    """Ein Locator mit festem Inhalt."""

    def __init__(self, text="", visible=True, kinder=None, items=None, evaluate=None,
                 evaluate_all=None, count=None, disabled=False, wait_fehler=None,
                 beim_klick=None):
        self.text = text
        self.visible = visible
        self.kinder = kinder or {}
        self.items = items
        self._evaluate = evaluate
        self._evaluate_all = evaluate_all
        self._count = count
        self.disabled = disabled
        self.wait_fehler = wait_fehler
        self.beim_klick = beim_klick
        self.klicks = 0
        self.gefuellt = []
        self.gewartet = []
        self.evaluate_aufrufe = []

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def nth(self, index):
        return self.items[index] if self.items is not None else self

    def all(self):
        return list(self.items or [])

    def count(self):
        if self._count is not None:
            return self._count
        if self.items is not None:
            return len(self.items)
        return 1 if self.visible else 0

    def locator(self, selektor):
        return self.kinder.get(selektor) or unsichtbar()

    def filter(self, **kwargs):
        return self.kinder.get("filter") or unsichtbar()

    def is_visible(self, timeout=None):
        if isinstance(self.visible, Exception):
            raise self.visible
        return self.visible

    def is_disabled(self):
        if isinstance(self.disabled, list):
            return self.disabled.pop(0)
        return self.disabled

    def wait_for(self, state="visible", timeout=None):
        self.gewartet.append(state)
        if self.wait_fehler:
            raise self.wait_fehler

    def click(self):
        self.klicks += 1
        if self.beim_klick:
            self.beim_klick()

    def fill(self, wert):
        self.gefuellt.append(wert)

    def inner_text(self):
        if isinstance(self.text, Exception):
            raise self.text
        return self.text

    def text_content(self):
        return self.text

    def evaluate(self, js, arg=None):
        self.evaluate_aufrufe.append((js, arg))
        if callable(self._evaluate):
            return self._evaluate(js, arg)
        return self._evaluate

    def evaluate_all(self, js):
        return self._evaluate_all


def unsichtbar():
    return Loc(visible=False, wait_fehler=PlaywrightTimeout("Timeout exceeded"))


class Uhr:
    def __init__(self):
        self.jetzt = 0.0

    def monotonic(self):
        return self.jetzt


class Seite:
    """Eine Playwright-Seite aus Attrappen."""

    def __init__(self, kinder=None, url="https://www.dfbnet.org/sria/", uhr=None):
        self.kinder = kinder or {}
        self.url = url
        self.uhr = uhr
        self.pausen = []
        self.tasten = []
        self.wait_function_aufrufe = []
        self.wait_function_fehler = None
        self.wait_selector_fehler = None
        self.keyboard = SimpleNamespace(press=self.tasten.append)

    def locator(self, selektor):
        return self.kinder.get(selektor) or unsichtbar()

    def wait_for_selector(self, selektor, timeout=None):
        if self.wait_selector_fehler:
            raise self.wait_selector_fehler

    def wait_for_timeout(self, ms):
        self.pausen.append(ms)
        if self.uhr:
            self.uhr.jetzt += ms / 1000

    def wait_for_function(self, js, arg=None, timeout=None, polling=None):
        self.wait_function_aufrufe.append({"js": js, "arg": arg, "timeout": timeout, "polling": polling})
        if self.wait_function_fehler:
            raise self.wait_function_fehler


@pytest.fixture
def uhr(monkeypatch):
    uhr = Uhr()
    monkeypatch.setattr(dfb_scraper, "time", SimpleNamespace(monotonic=uhr.monotonic))
    return uhr


def scraper_mit(seite, **kwargs):
    scraper = DFBScraper(**kwargs)
    scraper.page = seite
    return scraper


# ===== Login =====

USER_SEL = 'input[placeholder*="Benutzerkennung"], input[name*="username"]'
PASS_SEL = 'input[placeholder*="Passwort"], input[type="password"]'
SUBMIT_SEL = 'button:has-text("ANMELDEN")'
FEHLER_SEL = '.alert-error, .error, [class*="error"]'
FORMULAR_SEL = 'input[type="password"]'


def login_seite(url, fehler=None, formular_sichtbar=False):
    kinder = {USER_SEL: Loc(), PASS_SEL: Loc(), SUBMIT_SEL: Loc(),
              FORMULAR_SEL: Loc(visible=formular_sichtbar)}
    if fehler is not None:
        kinder[FEHLER_SEL] = fehler
    return Seite(kinder, url=url)


class TestLogin:
    @pytest.mark.parametrize("username, password", [(None, "pw"), ("kennung", None), ("", "")])
    def test_ohne_zugangsdaten(self, username, password):
        scraper = scraper_mit(login_seite("x"), username=username, password=password)
        with pytest.raises(ValueError):
            scraper.login()

    def test_erfolg_bei_weiterleitung(self):
        seite = login_seite("https://www.dfbnet.org/spielplus/start")
        scraper = scraper_mit(seite, username="test-kennung", password="test-passwort")

        scraper.login()

        assert seite.kinder[USER_SEL].gefuellt == ["test-kennung"]
        assert seite.kinder[PASS_SEL].gefuellt == ["test-passwort"]
        assert seite.kinder[SUBMIT_SEL].klicks == 1

    def test_fehlermeldung_von_dfbnet(self):
        seite = login_seite("https://auth.dfbnet.org/login",
                            fehler=Loc(text="Benutzerkennung oder Passwort ungueltig"))
        scraper = scraper_mit(seite, username="test-kennung", password="falsch")

        with pytest.raises(DFBCredentialsInvalidError) as fehler:
            scraper.login()

        assert fehler.value.details == "DFBnet meldet: Benutzerkennung oder Passwort ungueltig"
        assert fehler.value.status_code == 401

    def test_formular_noch_sichtbar(self):
        seite = login_seite("https://auth.dfbnet.org/login", formular_sichtbar=True)
        scraper = scraper_mit(seite, username="test-kennung", password="falsch")

        with pytest.raises(DFBCredentialsInvalidError):
            scraper.login()

    def test_kaputte_fehlerpruefung_wird_ignoriert(self):
        seite = login_seite("https://auth.dfbnet.org/login",
                            fehler=Loc(visible=PlaywrightTimeout("weg")), formular_sichtbar=True)
        scraper = scraper_mit(seite, username="test-kennung", password="falsch")

        with pytest.raises(DFBCredentialsInvalidError):
            scraper.login()

    def test_auf_auth_seite_ohne_formular_gilt_als_erfolg(self):
        seite = login_seite("https://auth.dfbnet.org/weiter", formular_sichtbar=False)
        scraper_mit(seite, username="test-kennung", password="test-passwort").login()

    def test_formular_erscheint_nicht(self):
        seite = login_seite("https://auth.dfbnet.org/login")
        seite.wait_selector_fehler = PlaywrightTimeout("kein Formular")
        scraper = scraper_mit(seite, username="test-kennung", password="test-passwort")

        with pytest.raises(PlaywrightTimeout):
            scraper.login()


class TestClickLogin:
    def test_erster_sichtbarer_selektor(self):
        knopf = Loc()
        seite = Seite({
            'button:has-text("Anmelden")': Loc(visible=PlaywrightTimeout("detached")),
            'a:has-text("Anmelden")': Loc(visible=False),
            '[href*="login"]': knopf,
        })

        scraper_mit(seite).click_login()

        assert knopf.klicks == 1

    def test_kein_knopf(self):
        with pytest.raises(Exception, match="Anmelden-Button nicht gefunden"):
            scraper_mit(Seite()).click_login()


class TestCookiesUndMenue:
    def test_cookie_banner_fehlt(self):
        scraper_mit(Seite()).accept_cookies()

    def test_cookie_banner_wird_geklickt(self):
        knopf = Loc()
        scraper_mit(Seite({'button:has-text("Alle akzeptieren")': knopf})).accept_cookies()
        assert knopf.klicks == 1
        assert knopf.gewartet == ["visible", "hidden"]

    def test_menue_schon_offen(self):
        seite = Seite()
        scraper_mit(seite).open_menu_if_needed()
        assert seite.pausen == []

    def test_menue_oeffnen(self):
        knopf = Loc()
        scraper_mit(Seite({'#dfb-Menu-toggle, button[ng-click*="menuBtnClicked"]': knopf})).open_menu_if_needed()
        assert knopf.klicks == 1


class TestReiter:
    def test_wechsel_ueber_id(self):
        knopf, inhalt = Loc(), Loc()
        seite = Seite({"button#coredata": knopf, "sria-coredata": inhalt})

        scraper_mit(seite).open_referee_tab("coredata", "sria-coredata")

        assert knopf.klicks == 1
        assert inhalt.gewartet == ["visible"]

    def test_inhalt_erscheint_nicht(self):
        seite = Seite({"button#coredata": Loc()})
        with pytest.raises(PlaywrightTimeout):
            scraper_mit(seite).open_referee_tab("coredata", "sria-coredata")


# ===== Stammdaten und QMax =====

def karte(felder, beschriftung=True, **kinder):
    k = {"div.row div.fw-700": Loc() if beschriftung else unsichtbar(),
         "div.fw-700": Loc() if beschriftung else unsichtbar()}
    k.update(kinder)
    return Loc(kinder=k, evaluate=felder)


class TestStammdaten:
    def test_liest_karten_und_hinweis(self):
        meldedaten = karte(
            {"SR-Gebiet": "Kreis Beispiel", "Verein": "FC Beispielstadt",
             "Umsatzsteuer­pflichtig": "nein", "Bemerkung": "-"},
            **{'div.row div.fw-700:has-text("FUSSBALL.DE")':
               Loc(text=" Ergebnisse duerfen auf FUSSBALL.DE erscheinen ")},
        )
        seite = Seite({
            "sria-coredata-id-photo-card": karte({"Ausweisnummer": " 12345 ", "Foto-Status": "gueltig"}),
            "sria-coredata-contact-details-card": karte({}, beschriftung=False),
            "sria-coredata-reporting-data-card": meldedaten,
        })

        daten = scraper_mit(seite).extract_stammdaten()

        assert daten["ausweisnummer"] == "12345"
        assert daten["foto_status"] == "gueltig"
        assert daten["ausweisgueltigkeit"] == ""
        assert daten["sr_gebiet"] == "Kreis Beispiel"
        assert daten["umsatzsteuerpflichtig"] == "nein"
        # "-" heisst bei DFBnet "wirklich leer" und bleibt stehen
        assert daten["bemerkung"] == "-"
        assert daten["fussball_de_hinweis"] == "Ergebnisse duerfen auf FUSSBALL.DE erscheinen"
        # Eine nicht geladene Karte liefert keine Felder - auch keine leeren
        assert "name_vorname" not in daten
        assert "telefon_mobil" not in daten
        assert meldedaten.evaluate_aufrufe[0][0] is DFBScraper._KARTEN_FELDER_JS

    def test_label_ohne_weiches_trennzeichen_wird_nicht_zugeordnet(self):
        seite = Seite({"sria-coredata-reporting-data-card": karte({"Umsatzsteuerpflichtig": "ja"})})
        assert scraper_mit(seite).extract_stammdaten()["umsatzsteuerpflichtig"] == ""

    def test_ohne_hinweis(self):
        seite = Seite({"sria-coredata-reporting-data-card": karte({"Verein": "FC X"})})
        assert "fussball_de_hinweis" not in scraper_mit(seite).extract_stammdaten()

    def test_keine_karte_geladen(self):
        assert scraper_mit(Seite()).extract_stammdaten() == {}

    def test_fehler_ergibt_leeres_dict(self):
        def kaputt(js, arg):
            raise RuntimeError("Execution context was destroyed")

        seite = Seite({"sria-coredata-id-photo-card": karte(kaputt)})
        assert scraper_mit(seite).extract_stammdaten() == {}


class TestQmax:
    def test_liest_werte(self):
        qkarte = karte({"QMax-SR:": " 7 ", "QMax-SRA1:": "8", "QMax-Beo.:": "-"})
        seite = Seite({"sria-qualifications-referee-qualifications-card": qkarte})

        assert scraper_mit(seite).extract_qmax() == {
            "qmax_sr": "7", "qmax_sra1": "8", "qmax_sra2": "", "qmax_beobachter": "-",
        }
        assert qkarte.evaluate_aufrufe[0][0] is DFBScraper._QMAX_FELDER_JS

    def test_evaluate_ohne_ergebnis(self):
        seite = Seite({"sria-qualifications-referee-qualifications-card": karte(None)})
        assert scraper_mit(seite).extract_qmax() == {
            "qmax_sr": "", "qmax_sra1": "", "qmax_sra2": "", "qmax_beobachter": "",
        }

    def test_karte_laedt_nicht(self):
        assert scraper_mit(Seite()).extract_qmax() == {}


# ===== Meine Spiele =====

SPIEL_SEL = "sria-matches-match-list-item"


class TestGetAllMatches:
    def test_wartet_auf_geladene_liste(self):
        seite = Seite({SPIEL_SEL: Loc(items=[Loc(), Loc(), Loc()])})

        assert scraper_mit(seite).get_all_matches() == 3

        aufruf, = seite.wait_function_aufrufe
        assert aufruf["js"] is DFBScraper._LISTE_GELADEN_JS
        assert aufruf["polling"] == 250
        # Keine feste Pause mehr - die ergab falsche "Keine Spiele gefunden"
        assert seite.pausen == []

    def test_liste_bleibt_leer(self):
        seite = Seite({SPIEL_SEL: Loc(items=[])})
        seite.wait_function_fehler = PlaywrightTimeout("45000ms")

        assert scraper_mit(seite).get_all_matches() == 0

    def test_geladen_js_wartet_auf_spinner_und_nachfrist(self):
        js = DFBScraper._LISTE_GELADEN_JS
        assert "dfb-spinner" in js
        assert "getClientRects" in js      # nur ein SICHTBARER Spinner haelt auf
        assert "> 3000" in js               # Nachfrist fuer eine wirklich leere Liste


class TestModals:
    def test_mehr_info_oeffnen(self):
        knopf = Loc()
        modal, anpfiff = Loc(), Loc()
        seite = Seite({
            SPIEL_SEL: Loc(items=[Loc(), Loc(kinder={"sria-matches-game-details-modal": knopf})]),
            ".dfb-modal": modal,
            ".dfb-modal .kickoff .fw-700": anpfiff,
        })

        scraper_mit(seite).open_mehr_info_modal(1)

        assert knopf.klicks == 1
        assert anpfiff.gewartet == ["visible"]

    def test_mehr_info_index_zu_gross(self):
        seite = Seite({SPIEL_SEL: Loc(items=[Loc()])})
        with pytest.raises(Exception, match="Spiel 2 nicht gefunden"):
            scraper_mit(seite).open_mehr_info_modal(1)

    @pytest.mark.parametrize("methode, kind", [
        ("open_mehr_info_modal", "sria-matches-game-details-modal"),
        ("open_referee_modal", "sria-matches-referees-contact-details-modal"),
        ("open_venue_modal", "sria-matches-venue-details-modal"),
    ])
    def test_knopf_nicht_sichtbar(self, methode, kind):
        seite = Seite({SPIEL_SEL: Loc(items=[Loc(kinder={kind: Loc(visible=False)})])})
        with pytest.raises(Exception, match="nicht sichtbar"):
            getattr(scraper_mit(seite), methode)(0)

    def test_schliessen_ueber_knopf(self):
        knopf = Loc()
        seite = Seite({'button[aria-label="Close"], .modal-close, [class*="close"]': knopf})

        scraper_mit(seite).close_modal()

        assert knopf.klicks == 1
        assert seite.tasten == []
        aufruf, = seite.wait_function_aufrufe
        assert aufruf["arg"] == DFBScraper._MODAL_SELEKTOR

    def test_schliessen_mit_escape(self):
        seite = Seite()
        scraper_mit(seite).close_modal()
        assert seite.tasten == ["Escape"]
        assert len(seite.wait_function_aufrufe) == 1

    def test_schliessen_rueckfall(self):
        seite = Seite({'button[aria-label="Close"], .modal-close, [class*="close"]': Loc()})
        seite.wait_function_fehler = PlaywrightTimeout("Modal bleibt offen")

        scraper_mit(seite).close_modal()

        assert seite.tasten == ["Escape"]
        assert seite.pausen == [1000]


def feld(wert, wert_selektor=".fw-700"):
    """Label-Div, dessen Elternelement den Wert traegt."""
    return Loc(kinder={"..": Loc(kinder={wert_selektor: Loc(text=wert)})})


class TestSpielinfo:
    def test_liest_modal(self):
        modal = Loc(kinder={
            ".kickoff .fw-700": Loc(text=" Sa., 21.11.2026 14:00 Uhr "),
            'div.text-color-grey-5:has-text("Heim")': feld(" FC Beispielstadt ", ".fs-lg.fw-700 span"),
            'div.text-color-grey-5:has-text("Gast")': feld("SV Musterdorf 2.", ".fs-lg.fw-700 span"),
            'div.text-color-grey-5:has-text("Mannschaftsart")': feld("Herren"),
            'div.text-color-grey-5:has-text("Spielklasse")': feld("Verbandsliga"),
            'div.text-color-grey-5:has-text("Spieltag")': feld("12"),
        })

        info = scraper_mit(Seite({".dfb-modal": modal})).extract_match_info_from_modal()

        assert info == {
            "anpfiff": "Sa., 21.11.2026 14:00 Uhr",
            "heim_team": "FC Beispielstadt",
            "gast_team": "SV Musterdorf 2.",
            "mannschaftsart": "Herren",
            "spielklasse": "Verbandsliga",
            "spieltag": "12",
        }

    def test_kein_modal(self):
        assert scraper_mit(Seite()).extract_match_info_from_modal() == {}


def kontaktzeile(wert, link=True):
    spalte = Loc(kinder={"a": Loc(text=wert)}) if link else Loc(text=wert)
    return Loc(kinder={"..": Loc(kinder={".col-7, .col-sm-6": spalte})})


TELEFON_SEL = r"text=/Telefon \(mobil\)|Telefon \(privat\)/"


def schiri(kopf, telefon=None, email=None, strasse=None, plz=None):
    kinder = {".mb-2.fw-700": Loc(text=kopf)}
    if telefon:
        zeile = kontaktzeile(telefon)
        kinder[TELEFON_SEL] = Loc(count=1, kinder=zeile.kinder)
    if email:
        kinder["text=E-Mail"] = Loc(kinder={"..": kontaktzeile(email).kinder[".."]})
    if strasse:
        kinder["text=Straße, Nr."] = kontaktzeile(strasse, link=False)
    if plz:
        kinder["text=PLZ, Ort"] = kontaktzeile(plz, link=False)
    return Loc(kinder=kinder)


class TestSchiedsrichter:
    def test_rollen_und_kontakte(self):
        personen = [
            schiri("SR Max Muster", telefon="0151 0000000", email="max@example.org",
                   strasse="Musterweg 1", plz="99999 Beispielstadt"),
            schiri("SRA 1 Erika Beispiel Probe"),
            schiri("SRA 2 Paul"),
            schiri("Beo Hans Pruefer"),
            schiri("Hinweis zum Gespann"),
        ]
        modal = Loc(kinder={"sria-matches-referee-contact-details-list-item": Loc(items=personen)})

        kontakte = scraper_mit(Seite({'.modal.show, [role="dialog"]': modal})).extract_referee_contacts()

        assert kontakte == [
            {"rolle": "SR", "name": "Max Muster", "telefon": "0151 0000000", "email": "max@example.org",
             "strasse": "Musterweg 1", "plz_ort": "99999 Beispielstadt"},
            {"rolle": "SRA 1", "name": "Erika Beispiel Probe"},
            {"rolle": "SRA 2", "name": "Paul"},
            {"rolle": "Beo", "name": "Hans Pruefer"},
        ]

    def test_kaputter_eintrag_wird_uebersprungen(self):
        kaputt = Loc(kinder={".mb-2.fw-700": Loc(visible=RuntimeError("detached"))})
        modal = Loc(kinder={"sria-matches-referee-contact-details-list-item":
                            Loc(items=[kaputt, schiri("SR Max Muster")])})

        kontakte = scraper_mit(Seite({'.modal.show, [role="dialog"]': modal})).extract_referee_contacts()

        assert kontakte == [{"rolle": "SR", "name": "Max Muster"}]

    def test_kein_modal(self):
        assert scraper_mit(Seite()).extract_referee_contacts() == []


class TestSpielstaette:
    def test_name_adresse_platz(self):
        geotag_eltern = Loc(kinder={"div": Loc(kinder={"filter": Loc(text=" Beispielstraße 5, 99999 Beispielstadt ")})})
        modal = Loc(kinder={
            "#modal-subtitle, .subtitle": Loc(text=" Sportplatz Am Beispielweg "),
            "dfb-geotag-icon": Loc(kinder={"..": Loc(kinder={"..": geotag_eltern})}),
            "text=/Rasenplatz|Kunstrasen|Hartplatz/": Loc(text="Kunstrasen"),
        })

        info = scraper_mit(Seite({'.modal.show, [role="dialog"]': modal})).extract_venue_info()

        assert info == {"name": "Sportplatz Am Beispielweg",
                        "adresse": "Beispielstraße 5, 99999 Beispielstadt",
                        "platz_typ": "Kunstrasen"}

    def test_rueckfaelle(self):
        geotag_eltern = Loc(kinder={"span": Loc(text="Halle Musterdorf")})
        modal = Loc(kinder={
            "#modal-subtitle, .subtitle": Loc(text=""),
            "dfb-geotag-icon": Loc(kinder={"..": Loc(kinder={"..": geotag_eltern})}),
            r"text=/\d{5}/": Loc(items=[Loc(text="99999"), Loc(text="99999 Musterdorf")]),
        })

        info = scraper_mit(Seite({'.modal.show, [role="dialog"]': modal})).extract_venue_info()

        assert info == {"name": "Halle Musterdorf", "adresse": "99999 Musterdorf"}

    def test_kein_modal(self):
        assert scraper_mit(Seite()).extract_venue_info() == {}


class TestScrapeAllMatches:
    def test_einzelne_spiele_duerfen_scheitern(self):
        scraper = scraper_mit(Seite())
        scraper.get_all_matches = lambda: 3
        geschlossen = []

        def mehr_info(index):
            if index == 1:
                raise Exception("Spiel 2 nicht gefunden")

        scraper.open_mehr_info_modal = mehr_info
        scraper.extract_match_info_from_modal = lambda: {"heim_team": "FC X", "gast_team": "SV Y"}
        scraper.open_referee_modal = lambda i: None
        scraper.extract_referee_contacts = lambda: [{"rolle": "SR"}]
        scraper.open_venue_modal = lambda i: None
        scraper.extract_venue_info = lambda: {"name": "Platz"}
        scraper.close_modal = lambda: geschlossen.append(1)
        fortschritt = []

        spiele = scraper.scrape_all_matches(lambda *a: fortschritt.append(a))

        assert len(spiele) == 2
        assert spiele[0] == {"spiel_info": {"heim_team": "FC X", "gast_team": "SV Y"},
                             "schiedsrichter": [{"rolle": "SR"}], "spielstaette": {"name": "Platz"}}
        # Der Aufrufer erkennt den unvollstaendigen Scrape an der Soll-Zahl
        assert scraper.erwartete_spiele == 3
        assert fortschritt[0] == (0, 3, "Scraping gestartet...")
        assert [f[0] for f in fortschritt] == [0, 1, 3]
        assert len(geschlossen) == 6


# ===== Dropdowns =====

def dropdown(optionen, wert=""):
    eintraege = [Loc() for _ in optionen]
    return Loc(kinder={
        "button.dropdown-item": Loc(items=eintraege, evaluate_all=list(optionen)),
        ".dropdown-toggle": Loc(),
        ".dfb-dropdown-input-value": Loc(text=wert),
    }), eintraege


class TestDropdown:
    def test_waehlt_ueber_index_nicht_teilstring(self):
        auswahl, eintraege = dropdown(["10 Ergebnisse pro Seite", "100 Ergebnisse pro Seite",
                                       "50 Ergebnisse pro Seite"])

        scraper_mit(Seite())._dropdown_waehlen(auswahl, "100 Ergebnisse pro Seite")

        assert auswahl.kinder[".dropdown-toggle"].klicks == 1
        assert [e.klicks for e in eintraege] == [0, 1, 0]

    def test_eintrag_fehlt(self):
        auswahl, eintraege = dropdown(["26/27", "25/26"])

        with pytest.raises(Exception, match="'24/25' nicht vorhanden"):
            scraper_mit(Seite())._dropdown_waehlen(auswahl, "24/25")
        assert auswahl.kinder[".dropdown-toggle"].klicks == 0

    def test_wert(self):
        assert DFBScraper._dropdown_wert(dropdown([], " 25/26 ")[0]) == "25/26"
        assert DFBScraper._dropdown_wert(dropdown([], None)[0]) == ""


# ===== Spieltabelle =====

def spiel(n):
    return {"datum_text": f"0{n}.09.2025", "heim": f"Heim {n}", "gast": f"Gast {n}"}


class TabellenZustand:
    """Liefert je Abfrage den naechsten Zustand (treffer, zeilen); der letzte bleibt stehen."""

    def __init__(self, scraper, zustaende):
        self.zustaende = list(zustaende)
        self.abfragen = 0
        scraper._treffer = self.treffer
        scraper._spielzeilen = self.zeilen

    def _aktuell(self):
        return self.zustaende[min(self.abfragen, len(self.zustaende) - 1)]

    def treffer(self):
        return self._aktuell()[0]

    def zeilen(self):
        zeilen = self._aktuell()[1]
        self.abfragen += 1
        return zeilen


class TestWarteAufSpieltabelle:
    def test_wartet_bis_spinner_weg_und_zeilen_neu(self, uhr):
        alt = [spiel(9)]
        neu = [spiel(1), spiel(2)]
        scraper = scraper_mit(Seite(uhr=uhr))
        zustand = TabellenZustand(scraper, [
            (None, alt),     # Spinner, alte Trefferzahl gilt nicht
            (2, alt),        # Zahl da, aber Tabelle noch nicht neu gerendert
            (2, neu),
        ])

        zeilen, treffer = scraper._warte_auf_spieltabelle(DFBScraper._zeilen_kennung(alt))

        assert (zeilen, treffer) == (neu, 2)
        assert zustand.abfragen == 3

    def test_seitengroesse_begrenzt_soll(self, uhr):
        seite1 = [spiel(i) for i in range(1, 6)]
        scraper = scraper_mit(Seite(uhr=uhr))
        TabellenZustand(scraper, [(12, seite1)])

        assert scraper._warte_auf_spieltabelle(None, seitengroesse=5) == (seite1, 12)

    def test_letzte_seite_ist_kuerzer(self, uhr):
        rest = [spiel(1), spiel(2)]
        scraper = scraper_mit(Seite(uhr=uhr))
        TabellenZustand(scraper, [(12, rest)])

        assert scraper._warte_auf_spieltabelle("vorher", erwartet=2, seitengroesse=5) == (rest, 12)
        assert uhr.jetzt == 0

    def test_gleiche_saison_erneut_gewaehlt(self, uhr):
        # Nichts aendert sich - nach der Frist gilt die Tabelle trotzdem als fertig
        zeilen = [spiel(1)]
        scraper = scraper_mit(Seite(uhr=uhr))
        TabellenZustand(scraper, [(1, zeilen)])

        assert scraper._warte_auf_spieltabelle(DFBScraper._zeilen_kennung(zeilen)) == (zeilen, 1)
        assert 5 < uhr.jetzt < 6

    def test_leere_saison(self, uhr):
        scraper = scraper_mit(Seite(uhr=uhr))
        TabellenZustand(scraper, [(None, []), (0, [])])

        assert scraper._warte_auf_spieltabelle(None) == ([], 0)
        assert uhr.jetzt < 45

    def test_timeout_liefert_was_da_ist(self, uhr):
        scraper = scraper_mit(Seite(uhr=uhr))
        TabellenZustand(scraper, [(85, [])])

        assert scraper._warte_auf_spieltabelle(None, timeout_ms=3000) == ([], 85)
        assert 3 <= uhr.jetzt < 3.5

    def test_zeilen_kennung(self):
        assert DFBScraper._zeilen_kennung([]) is None
        assert DFBScraper._zeilen_kennung([spiel(1), spiel(2)]) == "01.09.2025|Heim 1|Gast 1"


class TestBlaettern:
    def _scraper(self, vor_index, vor_knopf, seiten):
        knoepfe = Loc(items=[Loc(), Loc(), vor_knopf, Loc()])
        karte = Loc(evaluate=vor_index, kinder={"dfb-pagination button:not(.dropdown-item)": knoepfe})
        scraper = scraper_mit(Seite({DFBScraper._SPIELE_KARTE: karte}))
        scraper._spielzeilen = lambda: []
        aufrufe = []

        def warte(kennung, erwartet=None, seitengroesse=100):
            aufrufe.append(erwartet)
            return seiten.pop(0), 25

        scraper._warte_auf_spieltabelle = warte
        return scraper, aufrufe

    def test_sammelt_alle_seiten(self):
        vor = Loc()
        scraper, aufrufe = self._scraper(2, vor, [[spiel(2)] * 10, [spiel(3)] * 5])

        alle = scraper._blaettere_durch([spiel(1)] * 10, 25, 10)

        assert len(alle) == 25
        assert vor.klicks == 2
        assert aufrufe == [10, 5]

    def test_ohne_vor_knopf(self):
        scraper, aufrufe = self._scraper(-1, Loc(), [])
        assert scraper._blaettere_durch([spiel(1)], 25, 10) == [spiel(1)]
        assert aufrufe == []

    def test_deaktivierter_vor_knopf(self):
        vor = Loc(disabled=[False, True])
        scraper, _ = self._scraper(2, vor, [[spiel(2)] * 10])

        assert len(scraper._blaettere_durch([spiel(1)] * 10, 25, 10)) == 20
        assert vor.klicks == 1

    def test_leere_seite_beendet(self):
        scraper, _ = self._scraper(2, Loc(), [[]])
        assert len(scraper._blaettere_durch([spiel(1)] * 10, 25, 10)) == 10

    def test_reissleine(self):
        vor = Loc()
        scraper, _ = self._scraper(2, vor, [[spiel(2)]] * 50)
        scraper._blaettere_durch([spiel(1)] * 10, 25, 10)
        assert vor.klicks == 25 // 10 + 2


# ===== Saisons =====

class TestSaisonNamen:
    def test_liest_auswahlfeld(self):
        auswahl, _ = dropdown(["26/27", "25/26"])
        seite = Seite({DFBScraper._SPIELE_KARTE: Loc(kinder={"dfb-dropdown-input": auswahl})})
        assert scraper_mit(seite).extract_saison_namen() == ["26/27", "25/26"]

    def test_ohne_eintraege_kein_stilles_leeres_ergebnis(self):
        seite = Seite({DFBScraper._SPIELE_KARTE: Loc()})
        with pytest.raises(Exception, match="Kein Saison-Auswahlfeld"):
            scraper_mit(seite).extract_saison_namen()


def bilanz_roh(laedt=False, gewaehlt="25/26", einsaetze=(), lehrgaenge=()):
    kopf = [["Saison 25/26"], ["", "Geleitet", "Zurückgegeben", "Nicht angetreten"]]
    return {"laedt": laedt, "gewaehlt": gewaehlt,
            "einsaetze": kopf + [list(z) for z in einsaetze],
            "lehrgaenge": [["Saison 25/26"]] + [list(z) for z in lehrgaenge]}


DATEN = [("SR", "12", "1", "-"), ("SRA", "5", "-", "-"), ("Summe", "17", "1", "-")]


class TestBilanzAuswerten:
    def test_kopfzeilen_fallen_heraus(self):
        einsaetze, lehrgaenge = DFBScraper._bilanz_auswerten(bilanz_roh(
            einsaetze=DATEN + [("Geleitet", "x"), ("kurz",)],
            lehrgaenge=[("Lehrabend", "6"), ("Lehrabend (online)", "2"), ("Leistungsprüfung", "bestanden"),
                        ("Sonstiges", "1"), ("Lehrabend",)],
        ))

        assert einsaetze == [
            {"rolle": "SR", "geleitet": "12", "zurueckgegeben": "1", "nicht_angetreten": "-"},
            {"rolle": "SRA", "geleitet": "5", "zurueckgegeben": "-", "nicht_angetreten": "-"},
            {"rolle": "Summe", "geleitet": "17", "zurueckgegeben": "1", "nicht_angetreten": "-"},
        ]
        assert lehrgaenge == {"lehrabend": "6", "lehrabend_online": "2", "leistungspruefung": "bestanden"}

    def test_kurze_zeilen(self):
        einsaetze, _ = DFBScraper._bilanz_auswerten({"einsaetze": [["SR", "3"]]})
        assert einsaetze == [{"rolle": "SR", "geleitet": "3", "zurueckgegeben": "", "nicht_angetreten": ""}]

    def test_nur_kopfzeilen_ergibt_nichts(self):
        assert DFBScraper._bilanz_auswerten(bilanz_roh()) == ([], {})

    def test_geleitet_aus_summe(self):
        einsaetze, _ = DFBScraper._bilanz_auswerten(bilanz_roh(einsaetze=DATEN))
        assert DFBScraper._geleitet_laut_bilanz(einsaetze) == 17

    def test_geleitet_ohne_summe_aufaddiert(self):
        einsaetze, _ = DFBScraper._bilanz_auswerten(bilanz_roh(einsaetze=DATEN[:2] + [("4.OF", "-", "", "")]))
        assert DFBScraper._geleitet_laut_bilanz(einsaetze) == 17

    def test_geleitet_null(self):
        assert DFBScraper._geleitet_laut_bilanz([]) == 0
        assert DFBScraper._geleitet_laut_bilanz([{"rolle": "Summe", "geleitet": "-"}]) == 0


class TestSaisonBilanz:
    def _seite(self, zustaende, wert="26/27", optionen=("26/27", "25/26"), uhr=None):
        auswahl, eintraege = dropdown(optionen, wert)
        zustaende = list(zustaende)

        def auswerten(js, saison):
            assert js is DFBScraper._BILANZ_JS
            return zustaende.pop(0) if len(zustaende) > 1 else zustaende[0]

        karte = Loc(evaluate=auswerten, kinder={"dfb-dropdown-input": auswahl})
        return Seite({DFBScraper._BILANZ_KARTE: karte}, uhr=uhr), karte, auswahl, eintraege

    def test_wartet_ueber_kopfzeilen_hinaus_auf_daten(self, uhr):
        seite, karte, _, eintraege = self._seite([
            bilanz_roh(laedt=True, gewaehlt="26/27"),
            bilanz_roh(laedt=False, gewaehlt="25/26"),   # Kopf schon da, Daten noch nicht
            bilanz_roh(laedt=False, gewaehlt="25/26", einsaetze=DATEN, lehrgaenge=[("Lehrabend", "6")]),
        ], uhr=uhr)

        bilanz = scraper_mit(seite).extract_saison_bilanz("25/26")

        assert len(bilanz["einsaetze"]) == 3
        assert bilanz["lehrgaenge"] == {"lehrabend": "6"}
        assert len(karte.evaluate_aufrufe) == 3
        assert karte.evaluate_aufrufe[0][1] == "25/26"
        assert eintraege[1].klicks == 1

    def test_daten_der_falschen_saison_zaehlen_nicht(self, uhr):
        seite, karte, _, _ = self._seite([
            bilanz_roh(gewaehlt="26/27", einsaetze=DATEN),
            bilanz_roh(gewaehlt="25/26", einsaetze=DATEN),
        ], uhr=uhr)

        scraper_mit(seite).extract_saison_bilanz("25/26")

        assert len(karte.evaluate_aufrufe) == 2

    def test_spinner_haelt_auf(self, uhr):
        seite, karte, _, _ = self._seite([
            bilanz_roh(laedt=True, einsaetze=DATEN),
            bilanz_roh(laedt=False, einsaetze=DATEN),
        ], wert="25/26", uhr=uhr)

        scraper_mit(seite).extract_saison_bilanz("25/26")

        assert len(karte.evaluate_aufrufe) == 2

    def test_schon_gewaehlte_saison_wird_nicht_neu_gewaehlt(self, uhr):
        seite, _, auswahl, eintraege = self._seite([bilanz_roh(einsaetze=DATEN)], wert="25/26", uhr=uhr)

        scraper_mit(seite).extract_saison_bilanz("25/26")

        assert auswahl.kinder[".dropdown-toggle"].klicks == 0
        assert all(e.klicks == 0 for e in eintraege)

    def test_halb_geladene_karte_zaehlt_nicht(self, uhr):
        seite, _, _, _ = self._seite([bilanz_roh()], wert="25/26", uhr=uhr)

        assert scraper_mit(seite).extract_saison_bilanz("25/26", timeout_ms=2000) == \
            {"einsaetze": [], "lehrgaenge": {}}
        assert 2 <= uhr.jetzt < 2.5

    def test_saison_nicht_im_auswahlfeld(self, uhr):
        seite, _, _, _ = self._seite([bilanz_roh(einsaetze=DATEN)], uhr=uhr)
        assert scraper_mit(seite).extract_saison_bilanz("19/20") == {"einsaetze": [], "lehrgaenge": {}}

    def test_karte_laedt_nicht(self, uhr):
        assert scraper_mit(Seite(uhr=uhr)).extract_saison_bilanz("25/26") == {"einsaetze": [], "lehrgaenge": {}}


class TestSeitengroesse:
    def _scraper(self, ergebnisse, setzbar=(50, 20, 10)):
        scraper = scraper_mit(Seite())
        protokoll = {"gesetzt": [], "gelesen": []}

        def setze(groesse):
            if groesse not in setzbar:
                raise Exception("Eintrag nicht vorhanden")
            protokoll["gesetzt"].append(groesse)

        def lies(kennung, groesse):
            protokoll["gelesen"].append((kennung, groesse))
            return ergebnisse.pop(0)

        scraper._setze_seitengroesse = setze
        scraper._lies_seiten = lies
        scraper._eingestellte_seitengroesse = lambda: 100
        return scraper, protokoll

    def test_erste_groesse_reicht(self):
        scraper, protokoll = self._scraper([([spiel(1)] * 3, 3)])

        assert scraper._lies_spiele_mit_rueckfall("25/26", None, "k") == ([spiel(1)] * 3, 3, 50)
        assert protokoll["gesetzt"] == [50]
        # Nach dem Umstellen taugt die alte Kennung nicht mehr
        assert protokoll["gelesen"] == [(None, 50)]

    def test_eingestellte_groesse_wird_nicht_neu_gesetzt(self):
        scraper, protokoll = self._scraper([([spiel(1)], 1)])

        scraper._lies_spiele_mit_rueckfall("25/26", 50, "k")

        assert protokoll["gesetzt"] == []
        assert protokoll["gelesen"] == [("k", 50)]

    def test_leere_tabelle_bei_50_faellt_auf_20_zurueck(self):
        scraper, protokoll = self._scraper([([], 30), ([spiel(1)] * 30, 30)])

        zeilen, treffer, groesse = scraper._lies_spiele_mit_rueckfall("24/25", 50, "k")

        assert (len(zeilen), treffer, groesse) == (30, 30, 20)
        assert protokoll["gelesen"] == [("k", 50), (None, 20)]

    def test_nichts_klappt(self):
        scraper, _ = self._scraper([([], 30), ([], 30), ([spiel(1)], 30)])
        zeilen, treffer, groesse = scraper._lies_spiele_mit_rueckfall("24/25", 50, "k")
        assert (len(zeilen), treffer, groesse) == (1, 30, 10)

    def test_keine_groesse_setzbar(self):
        scraper, protokoll = self._scraper([([spiel(1)] * 7, 7)], setzbar=())

        assert scraper._lies_spiele_mit_rueckfall("25/26", None, "k") == ([spiel(1)] * 7, 7, None)
        assert protokoll["gelesen"] == [("k", 100)]

    def test_lies_seiten_blaettert_nur_bei_mehr_treffern(self):
        scraper = scraper_mit(Seite())
        scraper._warte_auf_spieltabelle = lambda k, seitengroesse: ([spiel(1)] * 10, 25)
        scraper._blaettere_durch = lambda zeilen, treffer, groesse: zeilen + [spiel(2)] * 15
        assert len(scraper._lies_seiten(None, 10)[0]) == 25

        scraper._warte_auf_spieltabelle = lambda k, seitengroesse: ([spiel(1)] * 10, 10)
        scraper._blaettere_durch = lambda *a: pytest.fail("darf nicht blaettern")
        assert len(scraper._lies_seiten(None, 10)[0]) == 10

    @pytest.mark.parametrize("wert, groesse", [
        ("50 Ergebnisse pro Seite", 50),
        ("", 100),
        ("viele", 100),
    ])
    def test_eingestellte_seitengroesse(self, wert, groesse):
        auswahl, _ = dropdown([], wert)
        seite = Seite({DFBScraper._SPIELE_KARTE: Loc(kinder={"dfb-dropdown-input": Loc(items=[Loc(), auswahl])})})
        assert scraper_mit(seite)._eingestellte_seitengroesse() == groesse

    def test_eingestellte_seitengroesse_ohne_auswahl(self):
        seite = Seite({DFBScraper._SPIELE_KARTE: Loc(kinder={"dfb-dropdown-input": Loc(items=[])})})
        assert scraper_mit(seite)._eingestellte_seitengroesse() == 100


class TestScrapeSaisons:
    def _scraper(self, saisons, spiele, bilanzen):
        karte = Loc(kinder={"table": Loc(), "dfb-dropdown-input": Loc(items=[Loc(), Loc()])})
        scraper = scraper_mit(Seite({DFBScraper._SPIELE_KARTE: karte}))
        gewaehlt = []
        scraper.extract_saison_namen = lambda: list(saisons)
        scraper._spielzeilen = lambda: []
        scraper._dropdown_waehlen = lambda dropdown, saison: gewaehlt.append(saison)

        def lies(saison, groesse, kennung):
            ergebnis = spiele[saison]
            if isinstance(ergebnis, Exception):
                raise ergebnis
            return ergebnis[0], ergebnis[1], 50

        scraper._lies_spiele_mit_rueckfall = lies
        scraper.extract_saison_bilanz = lambda saison: bilanzen.get(
            saison, {"einsaetze": [{"rolle": "Summe", "geleitet": str(len(spiele[saison][0]))}],
                     "lehrgaenge": {}})
        return scraper, gewaehlt

    def test_vollstaendige_saisons(self):
        scraper, gewaehlt = self._scraper(
            ["26/27", "25/26"],
            {"26/27": ([spiel(1)], 1), "25/26": ([spiel(1), spiel(2)], 2)},
            {},
        )
        fortschritt = []

        ergebnis = scraper.scrape_saisons(lambda *a: fortschritt.append(a))

        assert gewaehlt == ["26/27", "25/26"]
        assert ergebnis["25/26"] == {
            "spiele": [spiel(1), spiel(2)],
            "einsaetze": [{"rolle": "Summe", "geleitet": "2"}],
            "lehrgaenge": {},
            "vollstaendig": True,
            "erwartet": 2,
        }
        assert fortschritt == [(1, 2, "Saison 26/27 (1/2)"), (2, 2, "Saison 25/26 (2/2)")]

    def test_ueberspringt_fertige_aber_nie_die_laufende(self):
        scraper, gewaehlt = self._scraper(
            ["26/27", "25/26", "24/25"],
            {"26/27": ([spiel(1)], 1), "25/26": ([], 0), "24/25": ([], 0)},
            {},
        )

        ergebnis = scraper.scrape_saisons(ueberspringen={"26/27", "25/26"})

        assert gewaehlt == ["26/27", "24/25"]
        assert set(ergebnis) == {"26/27", "24/25"}

    def test_unvollstaendige_tabelle(self):
        scraper, _ = self._scraper(["25/26"], {"25/26": ([spiel(1)], 85)}, {})
        ergebnis = scraper.scrape_saisons()["25/26"]
        assert ergebnis["vollstaendig"] is False
        assert ergebnis["erwartet"] == 85

    def test_ohne_trefferzahl(self):
        scraper, _ = self._scraper(["25/26"], {"25/26": ([spiel(1)], None)}, {})
        ergebnis = scraper.scrape_saisons()["25/26"]
        assert ergebnis["vollstaendig"] is False
        assert ergebnis["erwartet"] == 1

    def test_ohne_bilanz_unvollstaendig(self):
        scraper, _ = self._scraper(["25/26"], {"25/26": ([spiel(1)], 1)},
                                   {"25/26": {"einsaetze": [], "lehrgaenge": {}}})
        assert scraper.scrape_saisons()["25/26"]["vollstaendig"] is False

    def test_leere_tabelle_aber_bilanz_kennt_spiele(self):
        # Sonst wuerde replace_saison eine Saison mit 12 Spielen leeren
        scraper, _ = self._scraper(["24/25"], {"24/25": ([], 0)},
                                   {"24/25": {"einsaetze": [{"rolle": "Summe", "geleitet": "12"}],
                                              "lehrgaenge": {}}})
        assert scraper.scrape_saisons()["24/25"]["vollstaendig"] is False

    def test_wirklich_leere_saison(self):
        scraper, _ = self._scraper(["24/25"], {"24/25": ([], 0)},
                                   {"24/25": {"einsaetze": [{"rolle": "Summe", "geleitet": "-"}],
                                              "lehrgaenge": {}}})
        ergebnis = scraper.scrape_saisons()["24/25"]
        assert ergebnis["vollstaendig"] is True
        assert ergebnis["spiele"] == []

    def test_fehler_in_einer_saison(self):
        scraper, _ = self._scraper(
            ["26/27", "25/26", "24/25"],
            {"26/27": ([spiel(1)], 1), "25/26": RuntimeError("Karte weg"), "24/25": ([spiel(2)], 1)},
            {},
        )
        assert set(scraper.scrape_saisons()) == {"26/27", "24/25"}


# ===== Beobachtungen und Spielberichte =====

class Kontext:
    def __init__(self):
        self.seiten = []

    def new_page(self):
        seite = SimpleNamespace(geschlossen=False)
        seite.close = lambda: setattr(seite, "geschlossen", True)
        self.seiten.append(seite)
        return seite


class TestScrapeBeobachtungen:
    def test_liest_jedes_modul_in_eigenem_tab(self, monkeypatch):
        startseite = SimpleNamespace(context=Kontext())
        scraper = scraper_mit(Seite())
        scraper.startseite = startseite
        gelesen = []

        monkeypatch.setattr(dfb_scraper, "finde_module",
                            lambda page: {"herren": "https://h", "portal": "https://p"})

        def lies_quelle(seite, quelle, url, saisons_fuer, progress):
            gelesen.append((quelle, url))
            if quelle == "portal":
                raise RuntimeError("Kein Suchformular")
            return {"25/26": {"beobachtungen": [], "vollstaendig": True}}

        monkeypatch.setattr(dfb_scraper, "lies_quelle", lies_quelle)

        ergebnis = scraper.scrape_beobachtungen(lambda q, s: s)

        assert ergebnis == {"herren": {"25/26": {"beobachtungen": [], "vollstaendig": True}}}
        assert gelesen == [("herren", "https://h"), ("portal", "https://p")]
        assert len(startseite.context.seiten) == 1
        assert startseite.context.seiten[0].geschlossen

    def test_ohne_startseite_die_aktuelle_seite(self, monkeypatch):
        seite = Seite()
        seite.context = Kontext()
        monkeypatch.setattr(dfb_scraper, "finde_module", lambda page: {})

        assert scraper_mit(seite).scrape_beobachtungen(lambda q, s: s) == {}
        assert seite.context.seiten[0].geschlossen


class TestScrapeSpielberichte:
    def test_nur_lesbare_und_benoetigte_berichte(self, monkeypatch):
        startseite = SimpleNamespace(context=Kontext())
        scraper = scraper_mit(Seite())
        scraper.startseite = startseite

        zeilen = {
            "25/26": {"zeilen": [
                {"dfb_spiel_id": "A", "lesbar": True, "neu": True},
                {"dfb_spiel_id": "B", "lesbar": False, "neu": True},
                {"dfb_spiel_id": "C", "lesbar": True, "neu": False},
            ]},
            "24/25": {"zeilen": [{"dfb_spiel_id": "A", "lesbar": True, "neu": True, "doppelt": True}]},
        }
        aufgerufen = {}

        monkeypatch.setattr(spielberichte, "finde_einsatzplan", lambda page: "https://plan")

        def lies_saisons(seite, url, saisons_fuer, progress):
            aufgerufen["plan"] = url
            return zeilen

        def lies_berichte(seite, zu_lesen, dokument_vorhanden, progress):
            aufgerufen["berichte"] = zu_lesen
            return {"A": {"daten": {}}}

        monkeypatch.setattr(spielberichte, "lies_saisons", lies_saisons)
        monkeypatch.setattr(spielberichte, "ist_lesbar", lambda zeile: zeile["lesbar"])
        monkeypatch.setattr(spielberichte, "lies_berichte", lies_berichte)

        ergebnis = scraper.scrape_spielberichte(lambda s: s, lambda zeile: zeile["neu"], lambda d: False)

        assert ergebnis == {"saisons": zeilen, "berichte": {"A": {"daten": {}}}}
        assert aufgerufen["plan"] == "https://plan"
        # Jedes Spiel nur einmal, auch wenn es in zwei Saisons steht
        assert aufgerufen["berichte"] == [zeilen["25/26"]["zeilen"][0]]
        assert [s.geschlossen for s in startseite.context.seiten] == [True, True]

    def test_ohne_zu_lesende_berichte_kein_app_tab(self, monkeypatch):
        startseite = SimpleNamespace(context=Kontext())
        scraper = scraper_mit(Seite())
        scraper.startseite = startseite

        monkeypatch.setattr(spielberichte, "finde_einsatzplan", lambda page: "https://plan")
        monkeypatch.setattr(spielberichte, "lies_saisons", lambda *a: {"25/26": {"zeilen": []}})
        monkeypatch.setattr(spielberichte, "lies_berichte", lambda *a: pytest.fail("darf nicht laufen"))

        ergebnis = scraper.scrape_spielberichte(lambda s: s, lambda z: True, lambda d: False)

        assert ergebnis == {"saisons": {"25/26": {"zeilen": []}}, "berichte": {}}
        assert len(startseite.context.seiten) == 1

    def test_tab_wird_auch_bei_fehler_geschlossen(self, monkeypatch):
        startseite = SimpleNamespace(context=Kontext())
        scraper = scraper_mit(Seite())
        scraper.startseite = startseite

        def kaputt(*args):
            raise TimeoutError("Einsatzplan laedt nicht")

        monkeypatch.setattr(spielberichte, "finde_einsatzplan", lambda page: "https://plan")
        monkeypatch.setattr(spielberichte, "lies_saisons", kaputt)

        with pytest.raises(TimeoutError):
            scraper.scrape_spielberichte(lambda s: s, lambda z: True, lambda d: False)
        assert startseite.context.seiten[0].geschlossen


class TestBrowserlebenszyklus:
    def test_stop_ohne_start(self):
        DFBScraper().stop()

    def test_start_startet_keinen_echten_browser(self):
        with pytest.raises(AssertionError, match="echten Browser"):
            DFBScraper().start()
