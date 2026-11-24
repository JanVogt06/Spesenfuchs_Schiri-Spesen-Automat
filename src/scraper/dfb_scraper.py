import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, Browser

# Füge src/ zum Path hinzu für Imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import setup_logger
from core.errors import DFBCredentialsInvalidError
from scraper.beobachtungen import finde_module, lies_quelle
from scraper import ansetzungen, saisons, spielberichte, sria_api, stammdaten

logger = setup_logger("dfb_scraper")


class DFBScraper:
    """Scraper für DFB.net Ansetzungen"""

    def __init__(self, headless: bool = True, username: str = None, password: str = None):
        """
        Initialisiert den Scraper.

        Args:
            headless: Browser im Hintergrund starten (False = sichtbar für Debugging)
            username: DFB.net Benutzername
            password: DFB.net Passwort
        """
        self.headless = headless
        self.username = username
        self.password = password
        self.browser: Browser | None = None
        self.page: Page | None = None

    def start(self):
        """Startet den Browser"""
        logger.info("Starte Browser...")

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)

        # Browser-Kontext mit fester Größe erstellen
        context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            screen={'width': 1920, 'height': 1080}
        )
        self.page = context.new_page()

        logger.info(f"Browser gestartet (headless={self.headless}, 1920x1080)")

    def stop(self):
        """Stoppt den Browser"""
        if self.browser:
            logger.info("Schließe Browser...")
            self.browser.close()
            self.playwright.stop()
            logger.info("Browser geschlossen")

    def open_dfbnet(self):
        """Öffnet die DFB.net Startseite"""
        logger.info("Öffne dfbnet.org...")

        # Weniger strikte Bedingung + längeres Timeout
        self.page.goto(
            "https://www.dfbnet.org",
            wait_until="domcontentloaded",
            timeout=60000
        )

        # Titel ausgeben
        title = self.page.title()
        logger.info(f"Seite geladen: {title}")

        return title

    def accept_cookies(self):
        """Akzeptiert das Cookie-Banner"""
        logger.info("Suche Cookie-Banner...")

        try:
            logger.info("Warte auf Cookie-Banner...")

            # Direkter, einfacherer Ansatz
            accept_button = self.page.locator('button:has-text("Alle akzeptieren")').first
            accept_button.wait_for(state="visible", timeout=30000)

            logger.info("Cookie-Banner gefunden, klicke...")
            accept_button.click()

            # Warte bis Banner VERSCHWUNDEN ist
            accept_button.wait_for(state="hidden", timeout=10000)
            logger.info("Cookies akzeptiert")

        except Exception as e:
            logger.warning(f"Cookie-Banner konnte nicht geklickt werden: {e}")
            logger.info("Fahre trotzdem fort...")

    def click_login(self):
        """Klickt auf den Anmelden-Button"""
        logger.info("Suche Anmelden-Button...")

        try:
            # Verschiedene Selektoren für "Anmelden" probieren
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
        """Füllt Login-Formular aus und meldet sich an"""
        logger.info("Fülle Login-Formular aus...")

        if not self.username or not self.password:
            logger.error("Username oder Passwort nicht gesetzt")
            raise ValueError("Username und Passwort müssen angegeben werden")

        try:
            # Warte bis Login-Formular sichtbar ist
            self.page.wait_for_selector('input[placeholder*="Benutzerkennung"], input[name*="username"]', timeout=20000)

            # Benutzername eingeben
            username_field = self.page.locator('input[placeholder*="Benutzerkennung"], input[name*="username"]').first
            username_field.fill(self.username)
            logger.info("Benutzername eingegeben")

            # Passwort eingeben
            password_field = self.page.locator('input[placeholder*="Passwort"], input[type="password"]').first
            password_field.fill(self.password)
            logger.info("Passwort eingegeben")

            # Anmelden-Button im Formular klicken
            login_submit = self.page.locator('button:has-text("ANMELDEN")').first
            login_submit.click()
            logger.info("Login-Button geklickt")

            # Warte und prüfe ob Login erfolgreich war
            logger.info("Warte auf Antwort vom Server...")
            self.page.wait_for_timeout(10000)

            # Prüfe mehrere Indikatoren für erfolgreichen Login
            current_url = self.page.url
            logger.info(f"Aktuelle URL nach Login: {current_url}")

            # 1. Prüfung: Sind wir auf einer anderen Domain?
            if "auth.dfbnet.org" not in current_url:
                logger.info("Login erfolgreich - Weitergeleitet zu DFBnet")
                return

            # 2. Prüfung: Gibt es eine Fehlermeldung?
            try:
                error_message = self.page.locator('.alert-error, .error, [class*="error"]').first
                if error_message.is_visible(timeout=2000):
                    error_text = error_message.inner_text()
                    logger.error(f"Login-Fehler: {error_text}")
                    # GEÄNDERT: Spezifische Exception werfen
                    raise DFBCredentialsInvalidError(f"DFBnet meldet: {error_text}")
            except DFBCredentialsInvalidError:
                raise  # Weiterleiten
            except:
                pass

            # 3. Prüfung: Ist Login-Formular noch sichtbar?
            if self.page.locator('input[type="password"]').is_visible(timeout=3000):
                logger.error("Login fehlgeschlagen - Login-Formular noch sichtbar")
                # GEÄNDERT: Spezifische Exception werfen
                raise DFBCredentialsInvalidError()

            # Wenn wir hier sind, war Login erfolgreich
            logger.info("Login erfolgreich")

        except DFBCredentialsInvalidError:
            raise  # Weiterleiten ohne zu wrappen
        except Exception as e:
            logger.error(f"Fehler beim Login: {e}")
            raise

    def open_menu_if_needed(self):
        """Öffnet das Menü, falls es noch geschlossen ist"""
        logger.info("Prüfe ob Menü geöffnet werden muss...")

        try:
            # Suche nach dem Menü-Button (nur bei kleinen Bildschirmen sichtbar)
            menu_button = self.page.locator('#dfb-Menu-toggle, button[ng-click*="menuBtnClicked"]').first

            # Prüfe ob Button existiert und sichtbar ist
            if menu_button.is_visible(timeout=3000):
                logger.info("Menü-Button gefunden, klicke...")
                menu_button.click()
                self.page.wait_for_timeout(2000)
                logger.info("Menü geöffnet")
            else:
                logger.info("Menü-Button nicht sichtbar - Menü bereits offen")

        except Exception as e:
            logger.info("Menü-Button nicht gefunden - Menü wahrscheinlich bereits offen")
            # Kein Fehler werfen, da dies normal ist bei großen Bildschirmen

    def navigate_to_schiriansetzung(self):
        """Navigiert zu Schiriansetzung -> Eigene Daten"""
        logger.info("Navigiere zu Schiriansetzung...")

        try:
            # Schritt 1: Auf "Schiriansetzung" klicken
            schiri_menu = self.page.locator('text=Schiriansetzung').first
            schiri_menu.wait_for(state="visible", timeout=15000)
            logger.info("Schiriansetzung-Menüpunkt gefunden, klicke...")
            schiri_menu.click()

            # Warte bis Untermenü SICHTBAR ist
            eigene_daten = self.page.locator('text=Eigene Daten').first
            eigene_daten.wait_for(state="visible", timeout=10000)

            # Schritt 2: Auf "Eigene Daten" klicken
            logger.info("Eigene Daten gefunden, klicke...")

            # Neuen Tab erwarten
            with self.page.context.expect_page() as new_page_info:
                eigene_daten.click()

            # Wechsle zum neuen Tab
            new_page = new_page_info.value
            new_page.wait_for_load_state("domcontentloaded", timeout=30000)

            # Die Startseite mit dem Hauptmenue bleibt offen und wird gemerkt:
            # die Beobachtungen laufen am Ende des Abrufs ueber deren Menue.
            self.startseite = self.page

            # Update page reference
            self.page = new_page

            # Ohne Query: nach dem Anmelde-Ruecksprung kann dort ein
            # Autorisierungscode stehen, und das Protokoll liegt auf der Platte.
            logger.info(f"Neue Seite geöffnet: {self.page.url.split('?')[0]}")
            logger.info("Erfolgreich zu Eigene Daten navigiert")

        except Exception as e:
            logger.error(f"Fehler beim Navigieren zu Schiriansetzung: {e}")
            raise

    def schiri_id(self) -> str:
        """
        Die eigene Schiedsrichter-ID - sobald die Ansetzungs-App angemeldet ist.

        Setzt voraus, dass navigate_to_schiriansetzung gelaufen ist. Alles,
        was danach aus der Schiriansetzung gelesen wird, kommt ueber deren
        JSON-Schnittstelle (scraper/sria_api.py); angeklickt wird dort nichts.
        """
        if not getattr(self, "_schiri_id", None):
            self._schiri_id = sria_api.warte_auf_app(self.page)
        return self._schiri_id

    def lies_stammdaten(self) -> dict:
        """Stammdaten und QMax-Werte (scraper/stammdaten.py)."""
        logger.info("Lese Stammdaten...")
        return stammdaten.lies_stammdaten(self.page, self.schiri_id())

    def scrape_saisons(self, progress_callback=None, ueberspringen=None) -> dict:
        """
        Geleitete Spiele und Bilanz je Saison (scraper/saisons.py).

        Args:
            ueberspringen: bereits vollstaendig gespeicherte Saisons; die
                laufende wird trotzdem gelesen.

        Returns:
            Dict saison -> {spiele, einsaetze, lehrgaenge, vollstaendig, erwartet}
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
        Liest die eigenen Beobachtungen aus Schiri-Beobachtung und Schiri-Portal.

        Laeuft als LETZTER Schritt des Abrufs. Die alten DFBnet-Module halten
        ihren Zustand in der Sitzung; im ersten Versuch lief dieser Schritt vor
        der Schiriansetzung, und danach klappte deren Menue nicht mehr auf -
        der ganze Abruf brach ab. Am Ende kann er nichts mehr kaputt machen.

        Die Einstiege stehen im Hauptmenue der Startseite, die
        navigate_to_schiriansetzung als self.startseite stehen laesst.
        Gelesen wird in einem eigenen Tab desselben Browser-Kontexts.

        Args:
            saisons_fuer: (quelle, angebotene Saisons) -> zu lesende Saisons
            progress_callback: wird als (aktuell, gesamt, schritt) aufgerufen

        Returns:
            quelle -> saison -> {"beobachtungen", "vollstaendig"}. Eine Quelle
            fehlt, wenn der Account das Modul nicht hat oder es nicht
            gelesen werden konnte.
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
        Liest die Spielberichte der eigenen Spiele - nur lesend.

        Erst der Einsatzplan aller noetigen Saisons (altes Formularmodul, in
        einem eigenen Tab), dann in einem weiteren Tab die Berichte ueber die
        JSON-Schnittstelle der Bericht-App. In der App wird nichts angeklickt;
        siehe scraper/spielberichte.py.

        Args:
            saisons_fuer: angebotene Saisons -> zu lesende Saisons
            braucht_bericht: Einsatzplan-Zeile -> soll der Bericht (neu) gelesen werden?
            dokument_vorhanden: dfb_dokument_id -> liegt die Datei schon vor?

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
        Liest alle Ansetzungen ueber die JSON-Schnittstelle der Ansetzungs-App.

        Setzt voraus, dass navigate_to_schiriansetzung gelaufen ist. Statt je
        Spiel drei Modals aufzuklicken, holt scraper/ansetzungen.py die Daten
        aller Spiele mit einer Handvoll Abrufen - und nicht nur fuer die
        zwei Wochen, die die Liste "Meine Spiele" anzeigt, sondern fuer die
        laufende Saison und ein Jahr voraus.

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

        # Wie viele Ansetzungen die Schnittstelle hergab. Der Aufrufer braucht
        # das, um einen unvollstaendigen Abruf zu erkennen: einzelne Spiele
        # koennen unten uebersprungen werden.
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
        """Context Manager: Automatisches Starten"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager: Automatisches Beenden"""
        self.stop()