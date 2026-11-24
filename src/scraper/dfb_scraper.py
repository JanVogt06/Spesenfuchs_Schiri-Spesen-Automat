import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, Browser

# Add src/ to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import setup_logger
from core.errors import DFBCredentialsInvalidError
from scraper.beobachtungen import finde_module, lies_quelle
from scraper import ansetzungen, saisons, spielberichte, sria_api, stammdaten

logger = setup_logger("dfb_scraper")


class DFBScraper:
    """Scraper for DFB.net assignments (Ansetzungen)"""

    def __init__(self, headless: bool = True, username: str = None, password: str = None):
        """
        Initializes the scraper.

        Args:
            headless: Start the browser in the background (False = visible, for debugging)
            username: DFB.net username
            password: DFB.net password
        """
        self.headless = headless
        self.username = username
        self.password = password
        self.browser: Browser | None = None
        self.page: Page | None = None

    def start(self):
        """Starts the browser"""
        logger.info("Starte Browser...")

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)

        # Create the browser context with a fixed size
        context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            screen={'width': 1920, 'height': 1080}
        )
        self.page = context.new_page()

        logger.info(f"Browser gestartet (headless={self.headless}, 1920x1080)")

    def stop(self):
        """Stops the browser"""
        if self.browser:
            logger.info("Schließe Browser...")
            self.browser.close()
            self.playwright.stop()
            logger.info("Browser geschlossen")

    def open_dfbnet(self):
        """Opens the DFB.net start page"""
        logger.info("Öffne dfbnet.org...")

        # Less strict condition + longer timeout
        self.page.goto(
            "https://www.dfbnet.org",
            wait_until="domcontentloaded",
            timeout=60000
        )

        # Log the title
        title = self.page.title()
        logger.info(f"Seite geladen: {title}")

        return title

    def accept_cookies(self):
        """Accepts the cookie banner"""
        logger.info("Suche Cookie-Banner...")

        try:
            logger.info("Warte auf Cookie-Banner...")

            # Direct, simpler approach
            accept_button = self.page.locator('button:has-text("Alle akzeptieren")').first
            accept_button.wait_for(state="visible", timeout=30000)

            logger.info("Cookie-Banner gefunden, klicke...")
            accept_button.click()

            # Wait until the banner has DISAPPEARED
            accept_button.wait_for(state="hidden", timeout=10000)
            logger.info("Cookies akzeptiert")

        except Exception as e:
            logger.warning(f"Cookie-Banner konnte nicht geklickt werden: {e}")
            logger.info("Fahre trotzdem fort...")

    def click_login(self):
        """Clicks the login ("Anmelden") button"""
        logger.info("Suche Anmelden-Button...")

        try:
            # Try various selectors for "Anmelden"
            selectors = [
                'button:has-text("Anmelden")',
                'a:has-text("Anmelden")',
                '[href*="login"]',
                'text=Anmelden',
                '.login',
                '#login'
            ]

            for selector in selectors:
                logger.info(f"Versuche Selektor: {selector}")
                try:
                    login_button = self.page.locator(selector).first
                    if login_button.is_visible(timeout=3000):
                        logger.info(f"Anmelden-Button gefunden mit: {selector}")
                        login_button.click()
                        self.page.wait_for_timeout(3000)
                        logger.info("Anmelden-Button geklickt")
                        return
                except:
                    continue

            logger.error("Anmelden-Button mit keinem Selektor gefunden")
            raise Exception("Anmelden-Button nicht gefunden")

        except Exception as e:
            logger.error(f"Fehler beim Klicken auf Anmelden: {e}")
            raise

    def login(self):
        """Fills in the login form and logs in"""
        logger.info("Fülle Login-Formular aus...")

        if not self.username or not self.password:
            logger.error("Username oder Passwort nicht gesetzt")
            raise ValueError("Username und Passwort müssen angegeben werden")

        try:
            # Wait until the login form is visible
            self.page.wait_for_selector('input[placeholder*="Benutzerkennung"], input[name*="username"]', timeout=20000)

            # Enter username
            username_field = self.page.locator('input[placeholder*="Benutzerkennung"], input[name*="username"]').first
            username_field.fill(self.username)
            logger.info("Benutzername eingegeben")

            # Enter password
            password_field = self.page.locator('input[placeholder*="Passwort"], input[type="password"]').first
            password_field.fill(self.password)
            logger.info("Passwort eingegeben")

            # Click the login button in the form
            login_submit = self.page.locator('button:has-text("ANMELDEN")').first
            login_submit.click()
            logger.info("Login-Button geklickt")

            # Wait and check whether the login succeeded
            logger.info("Warte auf Antwort vom Server...")
            self.page.wait_for_timeout(10000)

            # Check several indicators for a successful login
            current_url = self.page.url
            logger.info(f"Aktuelle URL nach Login: {current_url}")

            # Check 1: are we on a different domain?
            if "auth.dfbnet.org" not in current_url:
                logger.info("Login erfolgreich - Weitergeleitet zu DFBnet")
                return

            # Check 2: is there an error message?
            try:
                error_message = self.page.locator('.alert-error, .error, [class*="error"]').first
                if error_message.is_visible(timeout=2000):
                    error_text = error_message.inner_text()
                    logger.error(f"Login-Fehler: {error_text}")
                    # CHANGED: raise a specific exception
                    raise DFBCredentialsInvalidError(f"DFBnet meldet: {error_text}")
            except DFBCredentialsInvalidError:
                raise  # Re-raise
            except:
                pass

            # Check 3: is the login form still visible?
            if self.page.locator('input[type="password"]').is_visible(timeout=3000):
                logger.error("Login fehlgeschlagen - Login-Formular noch sichtbar")
                # CHANGED: raise a specific exception
                raise DFBCredentialsInvalidError()

            # If we get here, the login was successful
            logger.info("Login erfolgreich")

        except DFBCredentialsInvalidError:
            raise  # Re-raise without wrapping
        except Exception as e:
            logger.error(f"Fehler beim Login: {e}")
            raise

    def open_menu_if_needed(self):
        """Opens the menu if it is still closed"""
        logger.info("Prüfe ob Menü geöffnet werden muss...")

        try:
            # Look for the menu button (only visible on small screens)
            menu_button = self.page.locator('#dfb-Menu-toggle, button[ng-click*="menuBtnClicked"]').first

            # Check whether the button exists and is visible
            if menu_button.is_visible(timeout=3000):
                logger.info("Menü-Button gefunden, klicke...")
                menu_button.click()
                self.page.wait_for_timeout(2000)
                logger.info("Menü geöffnet")
            else:
                logger.info("Menü-Button nicht sichtbar - Menü bereits offen")

        except Exception as e:
            logger.info("Menü-Button nicht gefunden - Menü wahrscheinlich bereits offen")
            # Do not raise an error, as this is normal on large screens

    def navigate_to_schiriansetzung(self):
        """Navigates to Schiriansetzung -> Eigene Daten (referee assignment -> own data)"""
        logger.info("Navigiere zu Schiriansetzung...")

        try:
            # Step 1: click "Schiriansetzung"
            schiri_menu = self.page.locator('text=Schiriansetzung').first
            schiri_menu.wait_for(state="visible", timeout=15000)
            logger.info("Schiriansetzung-Menüpunkt gefunden, klicke...")
            schiri_menu.click()

            # Wait until the submenu is VISIBLE
            eigene_daten = self.page.locator('text=Eigene Daten').first
            eigene_daten.wait_for(state="visible", timeout=10000)

            # Step 2: click "Eigene Daten"
            logger.info("Eigene Daten gefunden, klicke...")

            # Expect a new tab
            with self.page.context.expect_page() as new_page_info:
                eigene_daten.click()

            # Switch to the new tab
            new_page = new_page_info.value
            new_page.wait_for_load_state("domcontentloaded", timeout=30000)

            # The start page with the main menu stays open and is remembered:
            # the observations (Beobachtungen) are read at the end of the fetch
            # via its menu.
            self.startseite = self.page

            # Update page reference
            self.page = new_page

            # Without the query: after the redirect back from the login an
            # authorization code may be in there, and the log is written to disk.
            logger.info(f"Neue Seite geöffnet: {self.page.url.split('?')[0]}")
            logger.info("Erfolgreich zu Eigene Daten navigiert")

        except Exception as e:
            logger.error(f"Fehler beim Navigieren zu Schiriansetzung: {e}")
            raise

    def schiri_id(self) -> str:
        """
        The user's own referee ID - as soon as the assignment app is logged in.

        Requires that navigate_to_schiriansetzung has run. Everything read from
        the Schiriansetzung afterwards comes through its JSON interface
        (scraper/sria_api.py); nothing is clicked there.
        """
        if not getattr(self, "_schiri_id", None):
            self._schiri_id = sria_api.warte_auf_app(self.page)
        return self._schiri_id

    def lies_stammdaten(self) -> dict:
        """Master data (Stammdaten) and QMax values (scraper/stammdaten.py)."""
        logger.info("Lese Stammdaten...")
        return stammdaten.lies_stammdaten(self.page, self.schiri_id())

    def scrape_saisons(self, progress_callback=None, ueberspringen=None) -> dict:
        """
        Officiated matches and balance per season (scraper/saisons.py).

        Args:
            ueberspringen: seasons that are already stored completely; the
                current one is read anyway.

        Returns:
            Dict season -> {spiele, einsaetze, lehrgaenge, vollstaendig, erwartet}
        """
        logger.info("=== Lese Saisonzusammenfassung ===")
        ergebnis = saisons.lies_saisons(
            self.page, self.schiri_id(), ueberspringen=ueberspringen,
            progress_callback=progress_callback,
        )
        logger.info(f"=== Saisonzusammenfassung: {len(ergebnis)} gelesen ===")
        return ergebnis

    def scrape_beobachtungen(self, saisons_fuer, progress_callback=None) -> dict:
        """
        Reads the user's own observations (Beobachtungen) from Schiri-Beobachtung
        and Schiri-Portal.

        Runs as the LAST step of the fetch. The old DFBnet modules keep their
        state in the session; in the first attempt this step ran before the
        Schiriansetzung, and afterwards its menu no longer opened - the whole
        fetch aborted. At the end it can no longer break anything.

        The entry points are in the main menu of the start page, which
        navigate_to_schiriansetzung leaves behind as self.startseite.
        Reading happens in a separate tab of the same browser context.

        Args:
            saisons_fuer: (source, offered seasons) -> seasons to read
            progress_callback: called as (current, total, step)

        Returns:
            source -> season -> {"beobachtungen", "vollstaendig"}. A source is
            missing if the account does not have the module or it could not be
            read.
        """
        logger.info("=== Lese Beobachtungen ===")

        startseite = getattr(self, "startseite", None) or self.page
        module = finde_module(startseite)
        logger.info(f"Beobachtungsmodule im Menue: {sorted(module)}")

        ergebnis = {}
        seite = startseite.context.new_page()

        try:
            for quelle, modul_url in module.items():
                try:
                    ergebnis[quelle] = lies_quelle(
                        seite, quelle, modul_url, saisons_fuer, progress_callback
                    )
                except Exception as e:
                    logger.warning(f"Beobachtungen {quelle} konnten nicht gelesen werden: {e}")
        finally:
            seite.close()

        return ergebnis

    def scrape_spielberichte(self, saisons_fuer, braucht_bericht, dokument_vorhanden,
                             progress_callback=None) -> dict:
        """
        Reads the match reports (Spielberichte) of the user's own matches -
        read-only.

        First the assignment schedule (Einsatzplan) of all required seasons (old
        form module, in a separate tab), then, in another tab, the reports via
        the JSON interface of the report app. Nothing is clicked in the app;
        see scraper/spielberichte.py.

        Args:
            saisons_fuer: offered seasons -> seasons to read
            braucht_bericht: schedule row -> should the report be (re-)read?
            dokument_vorhanden: dfb_dokument_id -> is the file already present?

        Returns:
            {"saisons": saison -> {"zeilen"}, "berichte": dfb_spiel_id -> {...}}
        """
        logger.info("=== Lese Spielberichte ===")

        startseite = getattr(self, "startseite", None) or self.page
        einsatzplan_url = spielberichte.finde_einsatzplan(startseite)

        liste = startseite.context.new_page()
        try:
            saisons = spielberichte.lies_saisons(
                liste, einsatzplan_url, saisons_fuer, progress_callback
            )
        finally:
            liste.close()

        zu_lesen = {}
        for daten in saisons.values():
            for zeile in daten["zeilen"]:
                if spielberichte.ist_lesbar(zeile) and braucht_bericht(zeile):
                    zu_lesen.setdefault(zeile["dfb_spiel_id"], zeile)

        logger.info(f"Spielberichte: {len(zu_lesen)} zu lesen")

        berichte = {}
        if zu_lesen:
            app = startseite.context.new_page()
            try:
                berichte = spielberichte.lies_berichte(
                    app, list(zu_lesen.values()), dokument_vorhanden, progress_callback
                )
            finally:
                app.close()

        logger.info(f"=== Spielberichte: {len(berichte)}/{len(zu_lesen)} gelesen ===")
        return {"saisons": saisons, "berichte": berichte}

    def scrape_all_matches(self, progress_callback=None):
        """
        Reads all assignments through the JSON interface of the assignment app.

        Requires that navigate_to_schiriansetzung has run. Instead of clicking
        open three modals per match, scraper/ansetzungen.py fetches the data of
        all matches with a handful of requests - and not only for the two weeks
        that the "Meine Spiele" list shows, but for the current season and a
        year ahead.

        Args:
            progress_callback: Optional callback function(current, total, step)
        """
        logger.info("=== Lese Ansetzungen ueber die Schnittstelle ===")

        if progress_callback:
            progress_callback(0, 0, "Lese Ansetzungen...")

        schiri_id = self.schiri_id()
        von, bis = ansetzungen.zeitraum()
        rohdaten = ansetzungen.hole_rohdaten(self.page, schiri_id, von, bis)
        anzahl_spiele = len(rohdaten["ansetzungen"])

        # How many assignments the interface returned. The caller needs this
        # to detect an incomplete fetch: individual matches can be skipped
        # below.
        self.erwartete_spiele = anzahl_spiele

        all_matches = []
        for ansetzung in rohdaten["ansetzungen"]:
            try:
                all_matches.append(ansetzungen.aufbereiten(ansetzung, rohdaten))
            except Exception as e:
                logger.error(f"Ansetzung {ansetzung.get('kickoff', '?')} nicht lesbar: {e}")

        if progress_callback:
            progress_callback(len(all_matches), anzahl_spiele,
                              f"{len(all_matches)} Ansetzungen gelesen")

        logger.info(f"=== Ansetzungen: {len(all_matches)}/{anzahl_spiele} gelesen "
                    f"({von:%d.%m.%Y} bis {bis:%d.%m.%Y}) ===")
        return all_matches

    def __enter__(self):
        """Context manager: starts automatically"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: stops automatically"""
        self.stop()