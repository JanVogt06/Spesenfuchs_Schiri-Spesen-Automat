"""
DFBScraper without a browser.

Instead of Playwright, the scraper gets a page made of stubs: Loc stands for
a locator and only knows the selectors a test gives it. Every other selector
yields an invisible locator whose wait_for runs into a timeout - like a page
on which the element never appears.

The waiting logic runs against a clock that only page.wait_for_timeout
advances. This allows dfb-spinner, "headers first, then data" and timeouts
to be played through without a test actually waiting.
"""
from datetime import date
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


# ===== Stubs =====

class PlaywrightTimeout(Exception):
    pass


class Loc:
    """A locator with fixed content."""

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
    """A Playwright page made of stubs."""

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


# ===== My matches =====


class TestScrapeAllMatches:
    """The assignments come from scraper/ansetzungen.py - here only the interplay."""

    def _rohdaten(self, n):
        return {"ansetzungen": [{"id": f"A{i}", "kickoff": "2026-11-14T14:00:00+01:00"} for i in range(n)]}

    def test_einzelne_ansetzungen_duerfen_scheitern(self, monkeypatch):
        aufrufe = []
        monkeypatch.setattr(dfb_scraper.sria_api, "warte_auf_app", lambda page: "SCHIRI")
        monkeypatch.setattr(dfb_scraper.ansetzungen, "zeitraum",
                            lambda: (date(2026, 6, 30), date(2027, 11, 24)))

        def rohdaten(page, schiri_id, von, bis):
            aufrufe.append((schiri_id, von, bis))
            return self._rohdaten(3)

        def aufbereiten(ansetzung, roh):
            if ansetzung["id"] == "A1":
                raise RuntimeError("Spiel zur Ansetzung nicht geliefert")
            return {"spiel_info": {"dfb_spiel_id": ansetzung["id"]}}

        monkeypatch.setattr(dfb_scraper.ansetzungen, "hole_rohdaten", rohdaten)
        monkeypatch.setattr(dfb_scraper.ansetzungen, "aufbereiten", aufbereiten)
        scraper = scraper_mit(Seite())
        fortschritt = []

        spiele = scraper.scrape_all_matches(lambda *a: fortschritt.append(a))

        assert [s["spiel_info"]["dfb_spiel_id"] for s in spiele] == ["A0", "A2"]
        assert aufrufe == [("SCHIRI", date(2026, 6, 30), date(2027, 11, 24))]
        # The caller recognizes the incomplete scrape by the target count
        assert scraper.erwartete_spiele == 3
        # The buffer day before the season is not fully covered
        assert scraper.gelesen_ab == "2026-07-01"
        assert fortschritt == [(0, 0, "Lese Ansetzungen..."), (2, 3, "2 Ansetzungen gelesen")]

    def test_schnittstelle_faellt_aus(self, monkeypatch):
        monkeypatch.setattr(dfb_scraper.sria_api, "warte_auf_app", lambda page: "SCHIRI")

        def kaputt(*a):
            raise dfb_scraper.sria_api.SitzungAbgelaufen("HTTP 401 auf match")

        monkeypatch.setattr(dfb_scraper.ansetzungen, "hole_rohdaten", kaputt)

        with pytest.raises(dfb_scraper.sria_api.SitzungAbgelaufen):
            scraper_mit(Seite()).scrape_all_matches()


# ===== Master data and seasons =====

class TestStammdatenUndSaisons:
    """The work is done by scraper/stammdaten.py and saisons.py - here only the interplay."""

    def test_schiri_id_wird_einmal_ermittelt(self, monkeypatch):
        aufrufe = []
        monkeypatch.setattr(dfb_scraper.sria_api, "warte_auf_app",
                            lambda page: aufrufe.append(page) or "SCHIRI")
        monkeypatch.setattr(dfb_scraper.stammdaten, "lies_stammdaten",
                            lambda page, schiri_id: {"qmax_sr": schiri_id})
        monkeypatch.setattr(dfb_scraper.saisons, "lies_saisons",
                            lambda page, schiri_id, ueberspringen=None, progress_callback=None:
                            {"26/27": {"schiri": schiri_id, "ueberspringen": ueberspringen}})
        scraper = scraper_mit(Seite())

        assert scraper.lies_stammdaten() == {"qmax_sr": "SCHIRI"}
        assert scraper.scrape_saisons(ueberspringen={"25/26"}) == {
            "26/27": {"schiri": "SCHIRI", "ueberspringen": {"25/26"}}}
        assert len(aufrufe) == 1


# ===== Observations and match reports =====

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
        # Each match only once, even if it appears in two seasons
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
