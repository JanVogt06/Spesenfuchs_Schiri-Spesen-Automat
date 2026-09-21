"""
Spesenfuchs - Main Entry Point
Startet die FastAPI Backend-Anwendung
"""
import os
from typing import Callable, Optional, List

# .env laden, bevor Module importiert werden, die Secrets beim Import lesen
from core.config import load_environment

load_environment()

from scraper.dfb_scraper import DFBScraper
from generator.docx_generator import KM_SATZ_EURO
from generator.spesen_calculator import calculate_spesen
from db.matches import upsert_match, mark_missing_matches, build_match_key
from db.stammdaten import upsert_stammdaten
from db.season import replace_saison, get_komplette_saisons
from utils.logger import setup_logger
from utils.match_utils import extract_iso_date_from_anpfiff, parse_saison_datum

logger = setup_logger("main")


def persist_matches(user_id: int, matches_data: List[dict], vollstaendig: bool = True) -> int:
    """
    Schreibt ein Scrape-Ergebnis in die Datenbank.

    Die Spesensaetze und der km-Satz werden hier eingefroren: sie gelten ab
    dem ersten Sehen eines Spiels und werden bei spaeteren Scrapes nicht mehr
    angefasst, damit eine Aenderung der Spesenordnung keine bereits
    abgegebene Abrechnung rueckwirkend umschreibt.

    Spiele, die nicht mehr in der Ansetzung stehen, werden markiert statt
    geloescht - sonst wuerden eingetragene Kilometer mit verschwinden.

    Args:
        vollstaendig: Ob der Scrape alle Ansetzungen erfasst hat. Nur dann darf
            aus "nicht im Ergebnis" auf "nicht mehr angesetzt" geschlossen
            werden. Der Scraper ueberspringt einzelne Spiele stillschweigend,
            wenn ein Modal auflaeuft; ohne diese Unterscheidung wuerden dem
            Nutzer voellig gueltige Ansetzungen als zurueckgezogen angezeigt.

    Returns:
        Anzahl gespeicherter Spiele.
    """
    seen_keys = []
    saved = 0

    for match_data in matches_data:
        try:
            spiel_info = match_data.get('spiel_info', {}) or {}
            spielstaette = match_data.get('spielstaette', {}) or {}
            datum = extract_iso_date_from_anpfiff(spiel_info.get('anpfiff', ''))

            sr_spesen, sra_spesen = calculate_spesen(
                spiel_info.get('spielklasse', ''),
                spiel_info.get('mannschaftsart', ''),
                spiel_info.get('staffel', '')
            )

            upsert_match(user_id, match_data, datum, sr_spesen, sra_spesen, KM_SATZ_EURO)
            seen_keys.append(build_match_key(spiel_info, spielstaette, datum))
            saved += 1

        except Exception as e:
            logger.error(f"Spiel konnte nicht gespeichert werden: {e}")
            continue

    if seen_keys and vollstaendig:
        markiert = mark_missing_matches(user_id, seen_keys)
        if markiert:
            logger.info(f"{markiert} Spiele nicht mehr in der Ansetzung - markiert")
    elif seen_keys:
        logger.warning(
            "Scrape war unvollstaendig - es wird kein Spiel als zurueckgezogen markiert"
        )

    logger.info(f"{saved}/{len(matches_data)} Spiele in der Datenbank")
    return saved


def persist_stammdaten(user_id: int, stammdaten: dict) -> None:
    """
    Schreibt die eigenen Stammdaten eines Users in die Datenbank.

    Fehler werden nur geloggt: die Ansetzungen sind das Produkt, die
    Stammdaten sind Beiwerk. Sie sollen einen Lauf nicht scheitern lassen,
    nachdem die Spiele bereits erfolgreich geschrieben wurden.

    Ein leeres Ergebnis wird uebersprungen statt gespeichert. Sonst legte der
    Upsert eine Zeile aus lauter Leerstrings an, und der Reiter zeigte dem
    Nutzer eine leere Tabelle statt des Hinweises, dass noch nichts abgerufen
    wurde.
    """
    if not any(stammdaten.values()):
        logger.warning("Keine Stammdaten gelesen - nichts zu speichern")
        return

    try:
        upsert_stammdaten(user_id, stammdaten)
        gefuellt = sum(1 for wert in stammdaten.values() if wert)
        logger.info(f"Stammdaten gespeichert ({gefuellt} Felder)")
    except Exception as e:
        logger.error(f"Stammdaten konnten nicht gespeichert werden: {e}")


def persist_saisons(user_id: int, saisons: dict) -> int:
    """
    Schreibt die gelesenen Saisons in die Datenbank - jede fuer sich ersetzend.

    Eine unvollstaendig gelesene Saison wird NICHT geschrieben. Die Tabellen
    werden pro Saison geleert und neu befuellt; mit einem halben Ergebnis
    wuerde dabei der gute Bestand vernichtet. Lieber bleibt der alte Stand
    stehen, bis der naechste Lauf die Saison sauber liest.

    Returns:
        Anzahl der ersetzten Saisons.
    """
    ersetzt = 0

    for saison, daten in saisons.items():
        if not daten.get("vollstaendig"):
            logger.warning(f"Saison {saison} unvollstaendig gelesen - bleibt unveraendert")
            continue

        try:
            spiele = []
            for roh in daten.get("spiele", []):
                datum, uhrzeit = parse_saison_datum(roh.get("datum_text", ""))
                gespann = roh.get("gespann") or []
                eigene = next((p.get("rolle", "") for p in gespann if p.get("selbst")), "")

                spiele.append({
                    "datum": datum,
                    "uhrzeit": uhrzeit,
                    "liga": roh.get("liga", ""),
                    "heim": roh.get("heim", ""),
                    "gast": roh.get("gast", ""),
                    "ergebnis": roh.get("ergebnis", ""),
                    "heim_gelb": roh.get("heim_gelb"),
                    "heim_gelbrot": roh.get("heim_gelbrot"),
                    "heim_rot": roh.get("heim_rot"),
                    "gast_gelb": roh.get("gast_gelb"),
                    "gast_gelbrot": roh.get("gast_gelbrot"),
                    "gast_rot": roh.get("gast_rot"),
                    "eigene_rolle": eigene,
                    "gespann": gespann,
                })

            geschrieben = replace_saison(
                user_id,
                saison,
                spiele=spiele,
                einsaetze=daten.get("einsaetze", []),
                lehrgaenge=daten.get("lehrgaenge", {}),
                erwartet=daten.get("erwartet"),
                vollstaendig=True,
            )
            ersetzt += 1
            logger.info(f"Saison {saison}: {geschrieben} Spiele gespeichert")

        except Exception as e:
            logger.error(f"Saison {saison} konnte nicht gespeichert werden: {e}")
            continue

    logger.info(f"{ersetzt}/{len(saisons)} Saisons in der Datenbank")
    return ersetzt


def scrape_matches(
    username: Optional[str] = None,
    password: Optional[str] = None,
    user_id: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[dict]:
    """
    Scrapt alle Ansetzungen des Users und schreibt sie in die Datenbank.

    Frueher wurde das Ergebnis zusaetzlich als spesen_data.json in einen
    Session-Ordner gelegt und daraus sofort je ein DOCX und ein PDF erzeugt.
    Beides entfaellt: die Datenbank ist die Quelle der Wahrheit, Dokumente
    entstehen erst beim Download.

    Args:
        username: DFB.net Benutzername (sonst aus ENV - nur fuer Entwicklung)
        password: DFB.net Passwort (sonst aus ENV - nur fuer Entwicklung)
        user_id: User, dem die Spiele gehoeren
        progress_callback: wird als (aktuell, gesamt, schritt) aufgerufen

    Returns:
        Die gescrapten Spiele (kann leer sein, z.B. in der Winterpause).
    """
    logger.info("=== DFB Scraper: Sammle alle Spieldaten ===")

    dfb_username = username or os.getenv("DFB_USERNAME")
    dfb_password = password or os.getenv("DFB_PASSWORD")

    if not dfb_username or not dfb_password:
        logger.error("DFB Credentials fehlen - weder als Parameter noch in ENV")
        return []

    def melde(current: int, total: int, step: str) -> None:
        if progress_callback:
            progress_callback(current, total, step)

    with DFBScraper(headless=True, username=dfb_username, password=dfb_password) as scraper:
        melde(0, 0, "Login und Navigation...")

        scraper.open_dfbnet()
        scraper.accept_cookies()
        scraper.click_login()
        scraper.accept_cookies()
        scraper.click_login()
        scraper.login()
        scraper.open_menu_if_needed()
        scraper.navigate_to_schiriansetzung()

        def fortschritt(current, total, step):
            melde(current, total, step)
            logger.info(f"Progress: {current}/{total} - {step}")

        all_matches = scraper.scrape_all_matches(progress_callback=fortschritt)

        # Hat der Scraper einzelne Spiele uebersprungen, ist das Ergebnis
        # unvollstaendig und taugt nicht als Grundlage fuer "nicht mehr
        # angesetzt"
        erwartet = getattr(scraper, "erwartete_spiele", len(all_matches))
        vollstaendig = len(all_matches) >= erwartet

        if not vollstaendig:
            logger.warning(
                f"Nur {len(all_matches)} von {erwartet} Ansetzungen gelesen - "
                "unvollstaendiger Scrape"
            )

        # Die Stammdaten liegen als weiterer Reiter in genau dem Tab, den
        # navigate_to_schiriansetzung schon gekapert hat - sie kosten also
        # keinen zweiten Login, nur zwei Klicks.
        #
        # Bewusst NACH den Spielen: der Tab startet auf "Meine Spiele", davor
        # eingeschoben braeuchte es einen Rueckklick samt erneutem Warten auf
        # die Spielliste, und jede Flakiness dort kostete den ganzen
        # Spiele-Scrape.
        #
        # Das eigene try/except, das nur warnt, ist tragend: persist_matches
        # laeuft erst nach dem with-Block. Eine Exception hier kaeme aus
        # scrape_matches heraus, und kein einziges Spiel waere gespeichert -
        # ein kompletter Nachtlauf verloren, weil DFBnet ein Stammdaten-Feld
        # verschoben hat.
        stammdaten = {}

        try:
            melde(len(all_matches), erwartet, "Lese Stammdaten...")

            scraper.open_referee_tab("coredata", "sria-coredata")
            stammdaten = scraper.extract_stammdaten()

            scraper.open_referee_tab(
                "qualifications", "sria-qualifications-referee-qualifications-card"
            )
            stammdaten.update(scraper.extract_qmax())

        except Exception as e:
            logger.warning(f"Stammdaten konnten nicht gelesen werden: {e}")

        # Und zum Schluss die Saisonzusammenfassung - wieder nur ein Reiter
        # weiter im selben Tab. Auch sie mit eigenem try/except: sie laeuft
        # ueber alle Saisons und ist damit der laengste Schritt, aber die
        # Ansetzungen sind das Produkt und duerfen daran nicht scheitern.
        saisons = {}

        try:
            melde(len(all_matches), erwartet, "Lese Saisonzusammenfassung...")

            scraper.open_referee_tab(
                "matches-statistics", "sria-matches-statistics-officiated-games-card"
            )
            # Abgeschlossene Saisons aendern sich nicht mehr - was vollstaendig
            # in der Datenbank steht, wird nicht noch einmal gelesen. Die
            # laufende Saison nimmt der Scraper selbst wieder aus der Liste.
            fertig = get_komplette_saisons(user_id) if user_id is not None else set()

            saisons = scraper.scrape_saisons(
                progress_callback=fortschritt, ueberspringen=fertig
            )

        except Exception as e:
            logger.warning(f"Saisonzusammenfassung konnte nicht gelesen werden: {e}")

    if user_id is not None:
        persist_matches(user_id, all_matches, vollstaendig=vollstaendig)
        persist_stammdaten(user_id, stammdaten)
        persist_saisons(user_id, saisons)

    logger.info(f"Erfolgreich {len(all_matches)} Spiele gescrapt")
    return all_matches


def main():
    """
    Startet die FastAPI Backend-Anwendung.
    Das Frontend läuft separat mit Vite Dev-Server.
    """
    import uvicorn

    # Port und Host aus Umgebungsvariablen laden
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8001"))  # Default: 8001 statt 8000

    logger.info("Starte Spesenfuchs API...")
    logger.info("==============================================")
    logger.info(f"API läuft auf: http://{API_HOST}:{API_PORT}")
    logger.info("==============================================")

    # Starte API
    uvicorn.run(
        "api.main_api:app",
        host=API_HOST,
        port=API_PORT,
        reload=False  # reload=False in Docker!
    )


if __name__ == "__main__":
    main()