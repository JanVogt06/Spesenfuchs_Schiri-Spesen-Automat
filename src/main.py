"""
Spesenfuchs - Main Entry Point
Startet die FastAPI Backend-Anwendung
"""
import os
import json
from pathlib import Path
from typing import Optional, Tuple, List

# .env laden, bevor Module importiert werden, die Secrets beim Import lesen
from core.config import load_environment

load_environment()

from scraper.dfb_scraper import DFBScraper
from generator.docx_generator import SpesenGenerator, KM_SATZ_EURO
from generator.spesen_calculator import calculate_spesen
from db.matches import upsert_match, mark_missing_matches, build_match_key
from utils.session_manager import SessionManager
from utils.logger import setup_logger
from utils.match_utils import extract_iso_date_from_anpfiff
from utils.pdf_converter import convert_docx_files_to_pdf

logger = setup_logger("main")


def persist_matches(user_id: int, matches_data: List[dict]) -> int:
    """
    Schreibt ein Scrape-Ergebnis in die Datenbank.

    Die Spesensaetze und der km-Satz werden hier eingefroren: sie gelten ab
    dem ersten Sehen eines Spiels und werden bei spaeteren Scrapes nicht mehr
    angefasst, damit eine Aenderung der Spesenordnung keine bereits
    abgegebene Abrechnung rueckwirkend umschreibt.

    Spiele, die nicht mehr in der Ansetzung stehen, werden markiert statt
    geloescht - sonst wuerden eingetragene Kilometer mit verschwinden.

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
                spiel_info.get('mannschaftsart', '')
            )

            upsert_match(user_id, match_data, datum, sr_spesen, sra_spesen, KM_SATZ_EURO)
            seen_keys.append(build_match_key(spiel_info, spielstaette, datum))
            saved += 1

        except Exception as e:
            logger.error(f"Spiel konnte nicht gespeichert werden: {e}")
            continue

    if seen_keys:
        markiert = mark_missing_matches(user_id, seen_keys)
        if markiert:
            logger.info(f"{markiert} Spiele nicht mehr in der Ansetzung - markiert")

    logger.info(f"{saved}/{len(matches_data)} Spiele in der Datenbank")
    return saved


def scrape_matches_with_session(
    session_path: Path = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    user_id: Optional[int] = None
) -> Tuple[Optional[List[dict]], Optional[Path]]:
    """
    Scrapt alle Spiele und speichert die Daten in einer Session.

    Args:
        session_path: Optional - spezifischer Session-Pfad
        username: DFB.net Benutzername (falls None, wird aus ENV geladen - nur für Entwicklung)
        password: DFB.net Passwort (falls None, wird aus ENV geladen - nur für Entwicklung)
        user_id: Optional - schreibt die Spiele in die Datenbank

    Returns:
        Tuple (matches_data, session_path)
    """
    logger.info("=== DFB Scraper: Sammle alle Spieldaten ===")

    # Session erstellen falls nicht vorhanden
    if not session_path:
        session_mgr = SessionManager()
        session_path = session_mgr.create_session()

    # Session Manager für Updates
    session_mgr = SessionManager()

    # Credentials: Parameter haben Vorrang, dann ENV als Fallback (nur für Entwicklung)
    dfb_username = username or os.getenv("DFB_USERNAME")
    dfb_password = password or os.getenv("DFB_PASSWORD")

    if not dfb_username or not dfb_password:
        logger.error("DFB Credentials fehlen - weder als Parameter noch in ENV")
        return None, None

    try:
        with DFBScraper(headless=True, username=dfb_username, password=dfb_password) as scraper:
            # Navigation und Login
            session_mgr.update_session_metadata(
                session_path,
                status="scraping",
                progress={"current": 0, "total": 0, "step": "Login und Navigation..."}
            )

            scraper.open_dfbnet()
            scraper.accept_cookies()
            scraper.click_login()
            scraper.accept_cookies()
            scraper.click_login()
            scraper.login()
            scraper.open_menu_if_needed()
            scraper.navigate_to_schiriansetzung()

            # Progress Callback für Scraping
            def update_scraping_progress(current, total, step):
                session_mgr.update_session_metadata(
                    session_path,
                    status="scraping",
                    progress={"current": current, "total": total, "step": step}
                )
                logger.info(f"Progress: {current}/{total} - {step}")

            # Alle Spiele scrapen MIT Progress-Callback
            all_matches = scraper.scrape_all_matches(progress_callback=update_scraping_progress)

            # Daten in Session speichern - AUCH BEI 0 SPIELEN!
            output_file = session_path / "spesen_data.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_matches, f, ensure_ascii=False, indent=2)

            logger.info(f"Daten gespeichert in: {output_file}")

            # Die Datenbank ist die kuenftige Quelle der Wahrheit; das JSON
            # bedient den Lesepfad noch, bis er umgestellt ist.
            if user_id is not None:
                try:
                    persist_matches(user_id, all_matches)
                except Exception as e:
                    logger.error(f"Spiele konnten nicht in die Datenbank geschrieben werden: {e}")

            logger.info(f"Erfolgreich {len(all_matches)} Spiele gescrapt")

            return all_matches, session_path

    except Exception as e:
        logger.error(f"Fehler beim Scraping: {e}")
        session_mgr.update_session_metadata(
            session_path,
            status="failed"
        )
        raise

def generate_documents_in_session(matches_data: List[dict], session_path: Path, user_id: int = None) -> List[Path]:
    """
    Generiert DOCX-Dokumente in einem Session-Ordner.

    Args:
        matches_data: Spieldaten
        session_path: Session-Ordner für Output
        user_id: Optional - laedt gespeicherte Fahrtkosten/OeVM des Users
                 und schreibt sie in die Dokumente

    Returns:
        Liste der generierten Dateipfade
    """
    logger.info("=== Spesenfuchs: Erstelle Dokumente ===")

    # Gespeicherte Fahrtkosten/OeVM des Users laden
    expenses_map = {}
    if user_id is not None:
        try:
            from db.database import get_all_match_expenses_for_user
            for entry in get_all_match_expenses_for_user(user_id):
                key = (entry['heim_team'], entry['gast_team'], entry['datum'])
                expenses_map[key] = entry
        except Exception as e:
            logger.error(f"Fehler beim Laden der Fahrtkosten: {e}")

    # Session Manager für Updates
    session_mgr = SessionManager()

    # Update: Starting document generation
    session_mgr.update_session_metadata(
        session_path,
        status="generating",
        progress={"current": 0, "total": len(matches_data), "step": "Erstelle Dokumente..."}
    )

    # Pfade
    project_root = Path(__file__).parent.parent
    template_path = project_root / "src" / "data" / "Spesenabrechnung_Vorlage.docx"

    # Generiere Dokumente im Session-Ordner
    generator = SpesenGenerator(template_path, session_path)
    generated_files = []

    from utils.match_utils import extract_iso_date_from_anpfiff

    for i, match_data in enumerate(matches_data, 1):
        try:
            spiel_info = match_data.get('spiel_info', {})
            expenses = expenses_map.get((
                spiel_info.get('heim_team', ''),
                spiel_info.get('gast_team', ''),
                extract_iso_date_from_anpfiff(spiel_info.get('anpfiff', '')),
            ))
            output_path = generator.generate_document(match_data, expenses=expenses)
            generated_files.append(output_path)

            # Update progress nach jedem Dokument
            session_mgr.update_session_metadata(
                session_path,
                status="generating",
                progress={
                    "current": i,
                    "total": len(matches_data),
                    "step": f"Dokument {i}/{len(matches_data)} erstellt"
                }
            )

        except Exception as e:
            logger.error(f"Fehler bei Dokument {i}: {e}")
            continue

    # PDF-Versionen aller Dokumente in einem Batch-Aufruf erzeugen (best-effort)
    if generated_files:
        try:
            convert_docx_files_to_pdf(generated_files)
        except Exception as e:
            logger.error(f"PDF-Konvertierung fehlgeschlagen: {e}")

    # Session-Metadata aktualisieren
    session_mgr.update_session_metadata(
        session_path,
        status="completed",
        files=[str(f.name) for f in generated_files],
        progress={
            "current": len(matches_data),
            "total": len(matches_data),
            "step": "Fertig!"
        }
    )

    logger.info(f"Fertig! {len(generated_files)} Dokumente erstellt in: {session_path}")
    return generated_files


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