"""
FastAPI Backend fuer Spesenfuchs
"""
import os
import sys
import json
import zipfile
import traceback
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import multiprocessing

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# .env laden, bevor Module importiert werden, die Secrets beim Import lesen
from core.config import load_environment

load_environment()

from scheduler import get_scheduler
from main import scrape_matches_with_session, generate_documents_in_session
from utils.session_manager import SessionManager
from utils.logger import setup_logger
from utils.match_utils import generate_filename_from_match, extract_iso_date_from_anpfiff
from utils.pdf_converter import convert_docx_files_to_pdf
from generator.docx_generator import SpesenGenerator
from generator.spesen_calculator import calculate_spesen, format_spesen
from db.scrape_runs import (
    start_run,
    update_run,
    get_latest_run,
    fail_stale_runs,
)
from db.database import (
    init_database,
    create_session as db_create_session,
    update_session_status as db_update_session_status,
    get_user_sessions,
    get_session_by_id as db_get_session_by_id,
    upsert_match_expenses,
    get_match_expenses,
    get_all_match_expenses_for_user,
    log_download
)
from api.auth import router as auth_router, get_current_user
from core.errors import (
    APIError,
    NotFoundError,
    AuthorizationError,
    CredentialsMissingError,
    api_error_handler,
    generic_exception_handler,
    DFBCredentialsInvalidError
)

logger = setup_logger("api")

# Wichtig fuer multiprocessing auf Windows
multiprocessing.freeze_support()


# ===== Lifespan Context Manager (ersetzt deprecated on_event) =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan Context Manager für Startup/Shutdown Events.
    Ersetzt die deprecated @app.on_event Decorator.
    """
    # === STARTUP ===
    init_database()
    logger.info("Datenbank initialisiert")

    # Laeufe, die der letzte Prozess nicht beenden konnte (Neustart, Absturz),
    # abschliessen - sonst pollt das Frontend ewig auf einen toten Lauf
    fail_stale_runs()

    # Scheduler starten
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("Automatischer Session-Scheduler gestartet")

    yield  # App läuft hier

    # === SHUTDOWN ===
    scheduler = get_scheduler()
    scheduler.stop()
    logger.info("Scheduler gestoppt")


app = FastAPI(title="Spesenfuchs API", lifespan=lifespan)

# Exception Handlers registrieren
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://spesen-generator.jan-vogt.dev",
        "http://localhost:5173",  # Für lokale Entwicklung
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Frontend Static Files (für Docker Production) =====
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", "./frontend/dist"))

if FRONTEND_DIR.exists():
    # Statische Assets (CSS, JS, Bilder)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
    logger.info(f"Frontend wird ausgeliefert von: {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend-Verzeichnis nicht gefunden: {FRONTEND_DIR}")

# Nach dem /assets Mount hinzufügen:
@app.get("/appicon.png")
async def serve_favicon():
    """Serve App Icon"""
    icon_path = FRONTEND_DIR / "appicon.png"
    if icon_path.exists():
        return FileResponse(str(icon_path), media_type="image/png")
    raise HTTPException(status_code=404, detail="Icon not found")

# Session Manager global
session_manager = SessionManager()

app.include_router(auth_router)


# ===== Request/Response Models =====

class GenerateRequest(BaseModel):
    """Request für Spesen-Generierung"""
    pass  # Credentials werden aus User-Profil geladen


class SessionResponse(BaseModel):
    """Response mit Session-Informationen"""
    session_id: str
    status: str
    files: List[Dict]
    download_all_url: str
    created_at: str
    progress: Optional[Dict] = None


# ===== Helper Functions =====

def _add_spesen_to_match(match: dict) -> dict:
    """
    Fügt berechnete Spesen-Informationen zu einem Match hinzu.

    Berechnet SR- und SRA-Spesen basierend auf Spielklasse und Mannschaftsart
    und fügt sie als _spesen Objekt zum Match hinzu.

    Args:
        match: Match-Dictionary mit spiel_info und schiedsrichter

    Returns:
        Match mit hinzugefügtem _spesen Objekt
    """
    spiel_info = match.get('spiel_info', {})
    schiedsrichter = match.get('schiedsrichter', [])

    spielklasse = spiel_info.get('spielklasse', '').lower()
    mannschaftsart = spiel_info.get('mannschaftsart', '')

    # Prüfe ob Punktspiel (nicht Pokal, nicht Freundschaft)
    is_punktspiel = 'pokal' not in spielklasse and 'freundschaft' not in spielklasse

    # Standard: keine Spesen
    spesen_info = {
        'sr': None,
        'sra': None,
        'sr_formatted': '',
        'sra_formatted': '',
        'is_punktspiel': is_punktspiel,
        'hinweis': None
    }

    if is_punktspiel:
        sr_spesen, sra_spesen = calculate_spesen(
            spiel_info.get('spielklasse', ''),
            mannschaftsart
        )

        if sr_spesen is not None:
            spesen_info['sr'] = sr_spesen
            spesen_info['sr_formatted'] = format_spesen(sr_spesen)

        if sra_spesen is not None:
            spesen_info['sra'] = sra_spesen
            spesen_info['sra_formatted'] = format_spesen(sra_spesen)

        # Prüfe ob SRAs angesetzt sind
        sra_count = sum(1 for sr in schiedsrichter if sr.get('rolle', '').startswith('SRA'))
        spesen_info['sra_count'] = sra_count

        # Hinweis wenn keine Spesen ermittelt werden konnten
        if sr_spesen is None:
            spesen_info['hinweis'] = 'Spesen konnten nicht automatisch ermittelt werden (überregionales Spiel oder unbekannte Spielklasse)'
    else:
        spesen_info['hinweis'] = 'Keine automatische Berechnung für Pokal-/Freundschaftsspiele'

    match['_spesen'] = spesen_info
    return match


# ===== Generation Process =====

def run_generation_process(
        session_path: Path,
        session_id: str,
        dfb_username: str,
        dfb_password: str,
        user_id: int = None,
        run_id: int = None
):
    """
    Führt die Generierung in einem separaten Prozess aus.

    Der Fortschritt wird in die Tabelle scrape_runs geschrieben - das ist der
    Kanal, ueber den die API den Poll des Frontends bedient. Die
    Session-Metadaten werden parallel weitergefuehrt, bis der Lesepfad
    umgestellt ist.
    """
    from utils.logger import setup_logger
    from core.errors import DFBCredentialsInvalidError

    process_logger = setup_logger("generation_process")
    sm = SessionManager()

    try:
        process_logger.info(f"Starte Generierung für Session {session_path.name}")

        sm.update_session_metadata(
            session_path,
            status="scraping",
            progress={"current": 0, "total": 0, "step": "Scraping gestartet..."}
        )
        db_update_session_status(session_id, "scraping")
        update_run(run_id, status="scraping", step="Scraping gestartet...")

        matches_data, _ = scrape_matches_with_session(
            session_path,
            username=dfb_username,
            password=dfb_password,
            user_id=user_id
        )

        # matches_data ist jetzt immer eine Liste (kann leer sein)
        if matches_data is None:
            matches_data = []

        if len(matches_data) > 0:
            sm.update_session_metadata(
                session_path,
                status="generating",
                progress={"current": 0, "total": len(matches_data), "step": "Erstelle Dokumente..."}
            )
            db_update_session_status(session_id, "generating")
            update_run(run_id, status="generating", step="Erstelle Dokumente...",
                       current=0, total=len(matches_data), matches_found=len(matches_data))

            generate_documents_in_session(matches_data, session_path, user_id)

            sm.update_session_metadata(session_path, status="completed")
            db_update_session_status(session_id, "completed")
            update_run(run_id, status="completed", step="Fertig!",
                       current=len(matches_data), total=len(matches_data),
                       matches_found=len(matches_data), finished=True)

            process_logger.info(f"Session {session_path.name} erfolgreich abgeschlossen mit {len(matches_data)} Spielen")
        else:
            # 0 Spiele ist OK (z.B. Winterpause) - trotzdem als "completed" markieren
            sm.update_session_metadata(
                session_path,
                status="completed",
                progress={"current": 0, "total": 0, "step": "Keine Spiele gefunden"}
            )
            db_update_session_status(session_id, "completed")
            update_run(run_id, status="completed", step="Keine Spiele gefunden",
                       matches_found=0, finished=True)

            process_logger.info(f"Session {session_path.name} abgeschlossen - keine Spiele vorhanden (Winterpause?)")

    except DFBCredentialsInvalidError as e:
        # SPEZIFISCH: DFB-Credentials ungültig
        process_logger.error(f"DFB-Login fehlgeschlagen: {e.message}")
        sm.update_session_metadata(
            session_path,
            status="failed",
            progress={
                "current": 0,
                "total": 0,
                "step": "Fehler",
                "error_code": "DFB_CREDENTIALS_INVALID",
                "error_message": "Die DFBnet-Zugangsdaten sind ungültig. Bitte prüfe Benutzername und Passwort in den Einstellungen."
            }
        )
        db_update_session_status(session_id, "failed")
        update_run(run_id, status="failed", step="Fehler",
                   error_code="DFB_CREDENTIALS_INVALID",
                   error_message="Die DFBnet-Zugangsdaten sind ungültig. Bitte prüfe Benutzername und Passwort in den Einstellungen.",
                   finished=True)

    except Exception as e:
        # GENERISCH: Anderer Fehler
        process_logger.error(f"Fehler in Session {session_path.name}: {e}")
        sm.update_session_metadata(
            session_path,
            status="failed",
            progress={
                "current": 0,
                "total": 0,
                "step": "Fehler",
                "error_code": "GENERATION_ERROR",
                "error_message": "Bei der Generierung ist ein Fehler aufgetreten."
            }
        )
        db_update_session_status(session_id, "failed")
        update_run(run_id, status="failed", step="Fehler",
                   error_code="GENERATION_ERROR",
                   error_message="Bei der Generierung ist ein Fehler aufgetreten.",
                   finished=True)


@app.post("/api/generate", response_model=SessionResponse)
async def generate_spesen(
    request: GenerateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Startet die Spesen-Generierung in einer neuen Session.
    Nur fuer eingeloggte User.
    DFB-Credentials werden automatisch aus User-Profil geladen.
    """
    user_id = current_user['id']
    logger.info(f"User {current_user['email']} startet Generierung")

    # Lade DFB-Credentials aus DB
    from db.database import get_dfb_credentials
    from core.encryption import decrypt_credential

    dfb_creds = get_dfb_credentials(user_id)

    if not dfb_creds:
        raise CredentialsMissingError()

    # Entschluesseln
    dfb_username = decrypt_credential(dfb_creds['dfb_username_encrypted'])
    dfb_password = decrypt_credential(dfb_creds['dfb_password_encrypted'])

    # Laeufe, deren Prozess gestorben ist, vorher abraeumen - sonst haengt
    # der Poll des Frontends am alten Lauf fest
    fail_stale_runs()

    # Neue Session erstellen
    session_path = session_manager.create_session()
    session_id = session_path.name

    # Session in DB speichern mit User-Verknuepfung
    db_create_session(session_id, user_id)
    run_id = start_run(user_id)

    # Generierung in eigenem Prozess starten (fuer Playwright-Kompatibilitaet)
    # Credentials werden direkt als Parameter übergeben (nicht über ENV!)
    process = multiprocessing.Process(
        target=run_generation_process,
        args=(session_path, session_id, dfb_username, dfb_password, user_id, run_id),
        daemon=True
    )
    process.start()

    return SessionResponse(
        session_id=session_id,
        status="in_progress",
        files=[],
        download_all_url=f"/api/download/{session_id}/all",
        created_at=datetime.now().isoformat(),
        progress={"current": 0, "total": 0, "step": "Starte..."}
    )


@app.get("/api/scrape/status")
async def get_scrape_status(current_user: dict = Depends(get_current_user)):
    """
    Aktueller Stand des juengsten Scrape-Laufs. Ersetzt den Poll auf die
    Session-Metadaten.

    error_code traegt weiterhin DFB_CREDENTIALS_INVALID, damit das Frontend
    den User wie bisher in die Einstellungen schicken kann.
    """
    # Abgestuerzte Laeufe abraeumen, damit der Poll nicht ewig auf
    # "scraping" stehen bleibt
    fail_stale_runs()

    run = get_latest_run(current_user['id'])
    if not run:
        return {"status": "idle", "progress": None}

    return {
        "run_id": run['id'],
        "status": run['status'],
        "matches_found": run['matches_found'],
        "started_at": run['started_at'],
        "finished_at": run['finished_at'],
        "progress": {
            "current": run['current_item'],
            "total": run['total_items'],
            "step": run['step'],
            "error_code": run['error_code'],
            "error_message": run['error_message'],
        },
    }


@app.get("/api/sessions", response_model=List[SessionResponse])
async def get_user_sessions_list(current_user: dict = Depends(get_current_user)):
    """
    Gibt alle Sessions des eingeloggten Users zurueck.
    """
    user_id = current_user['id']

    # Hole Sessions aus DB
    db_sessions = get_user_sessions(user_id)

    # Erweitere mit Dateisystem-Infos
    response_sessions = []
    for db_session in db_sessions:
        session_id = db_session['session_id']
        session_path = session_manager.get_session_by_id(session_id)

        if not session_path:
            continue

        # Lade Metadata aus Dateisystem
        metadata_path = session_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            metadata = {}

        files = session_manager.get_session_files(session_path)

        response_sessions.append(SessionResponse(
            session_id=session_id,
            status=db_session['status'],
            files=files,
            download_all_url=f"/api/download/{session_id}/all",
            created_at=db_session['created_at'],
            progress=metadata.get("progress")
        ))

    return response_sessions


@app.get("/api/matches")
async def get_all_user_matches(current_user: dict = Depends(get_current_user)):
    """
    Gibt alle Spiele des Users zurück (dedupliziert über alle Sessions).
    """
    user_id = current_user['id']

    try:
        db_sessions = get_user_sessions(user_id)
        logger.info(f"Lade Matches für User {user_id}, {len(db_sessions)} Sessions gefunden")

        # Gespeicherte Fahrtkosten/OeVM des Users
        expenses_map = {
            (e['heim_team'], e['gast_team'], e['datum']): e
            for e in get_all_match_expenses_for_user(user_id)
        }

        all_matches_dict = {}

        for db_session in db_sessions:
            session_id = db_session['session_id']
            session_path = session_manager.get_session_by_id(session_id)

            if not session_path or not session_path.exists():
                logger.warning(f"Session-Pfad nicht gefunden: {session_id}")
                continue

            matches_file = session_path / "spesen_data.json"
            if not matches_file.exists():
                logger.warning(f"spesen_data.json nicht gefunden in {session_id}")
                continue

            try:
                with open(matches_file, 'r', encoding='utf-8') as f:
                    session_matches = json.load(f)

                logger.info(f"Session {session_id}: {len(session_matches)} Spiele geladen")

                for match in session_matches:
                    spiel_info = match.get('spiel_info', {})
                    heim = spiel_info.get('heim_team', '')
                    gast = spiel_info.get('gast_team', '')

                    if not heim or not gast:
                        logger.warning(f"Spiel ohne Heim/Gast-Team in {session_id}")
                        continue

                    # Generiere Dateinamen mit zentraler Helper-Funktion
                    filename = generate_filename_from_match(match)

                    # Prüfe ob Datei existiert
                    file_path = session_path / filename
                    if not file_path.exists():
                        logger.warning(f"Datei nicht gefunden: {filename} in {session_id}")
                        continue

                    # Extrahiere Datum für Deduplizierung und Sortierung
                    datum = extract_iso_date_from_anpfiff(spiel_info.get('anpfiff', ''))
                    key = (heim, gast, datum)

                    # Deduplizierung: Neuere Session gewinnt
                    if key not in all_matches_dict or db_session['created_at'] > all_matches_dict[key]['_created_at']:
                        match['_session_id'] = session_id
                        match['_datum'] = datum
                        match['_created_at'] = db_session['created_at']
                        match['_filename'] = filename
                        match['_pdf_available'] = file_path.with_suffix('.pdf').exists()
                        match['_expenses'] = expenses_map.get(key)
                        # Spesen hinzufügen
                        _add_spesen_to_match(match)
                        all_matches_dict[key] = match

            except Exception as e:
                logger.error(f"Fehler beim Lesen von {matches_file}: {e}")
                logger.error(traceback.format_exc())
                continue

        # Konvertiere zu Liste und sortiere nach Datum (neueste zuerst)
        matches_list = list(all_matches_dict.values())
        matches_list.sort(key=lambda x: x['_datum'], reverse=True)

        logger.info(f"Gesamt: {len(matches_list)} deduplizierte Spiele für User {user_id}")
        return JSONResponse(content=matches_list)

    except Exception as e:
        logger.error(f"Fehler beim Laden aller Matches: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


class MatchExpensesRequest(BaseModel):
    session_id: str
    heim_team: str
    gast_team: str
    datum: str  # ISO-Datum (YYYY-MM-DD)
    sr_km: Optional[float] = None
    sr_oevm: Optional[float] = None
    sra1_km: Optional[float] = None
    sra1_oevm: Optional[float] = None
    sra2_km: Optional[float] = None
    sra2_oevm: Optional[float] = None


@app.post("/api/matches/expenses")
async def save_match_expenses(
        request: MatchExpensesRequest,
        current_user: dict = Depends(get_current_user)
):
    """
    Speichert Fahrtkosten (km) und OeVM fuer ein Spiel und generiert
    das Dokument (DOCX + PDF) sofort neu.
    """
    user_id = current_user['id']

    # Session pruefen
    db_session = db_get_session_by_id(request.session_id)
    if not db_session:
        raise NotFoundError("Session nicht gefunden")
    if db_session['user_id'] != user_id:
        raise AuthorizationError("Diese Session gehört einem anderen User")

    session_path = session_manager.get_session_by_id(request.session_id)
    if not session_path:
        raise NotFoundError("Session nicht gefunden")

    # Werte validieren
    expense_keys = ['sr_km', 'sr_oevm', 'sra1_km', 'sra1_oevm', 'sra2_km', 'sra2_oevm']
    expenses = {key: getattr(request, key) for key in expense_keys}
    for key, value in expenses.items():
        if value is not None and (value < 0 or value > 99999):
            raise HTTPException(status_code=400, detail=f"Ungültiger Wert für {key}")

    # In DB speichern (ueberlebt naechtliche Neu-Scrapes)
    upsert_match_expenses(user_id, request.heim_team, request.gast_team, request.datum, expenses)

    # Match in den Session-Daten finden
    data_file = session_path / "spesen_data.json"
    if not data_file.exists():
        raise NotFoundError("Spieldaten der Session nicht gefunden")

    with open(data_file, 'r', encoding='utf-8') as f:
        matches_data = json.load(f)

    match = next(
        (m for m in matches_data
         if m.get('spiel_info', {}).get('heim_team') == request.heim_team
         and m.get('spiel_info', {}).get('gast_team') == request.gast_team
         and extract_iso_date_from_anpfiff(m.get('spiel_info', {}).get('anpfiff', '')) == request.datum),
        None
    )
    if not match:
        raise NotFoundError("Spiel in dieser Session nicht gefunden")

    # Dokument sofort neu generieren
    try:
        template_path = Path(__file__).parent.parent / "data" / "Spesenabrechnung_Vorlage.docx"
        generator = SpesenGenerator(template_path, session_path)
        docx_path = generator.generate_document(match, expenses=expenses)
    except Exception as e:
        logger.error(f"Fehler beim Neu-Generieren des Dokuments: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Dokument konnte nicht neu generiert werden")

    # PDF neu erzeugen (best-effort)
    pdf_available = False
    try:
        results = convert_docx_files_to_pdf([docx_path])
        pdf_available = results.get(docx_path, False)
    except Exception as e:
        logger.error(f"PDF-Konvertierung fehlgeschlagen: {e}")

    return {
        "success": True,
        "filename": docx_path.name,
        "pdf_available": pdf_available,
    }


@app.get("/api/session/{session_id}", response_model=SessionResponse)
async def get_session_status(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Gibt den Status einer Session zurueck.
    """
    user_id = current_user['id']

    # Pruefe ob Session dem User gehoert
    db_session = db_get_session_by_id(session_id)

    if not db_session:
        raise NotFoundError("Session nicht gefunden")

    if db_session['user_id'] != user_id:
        raise AuthorizationError("Diese Session gehört einem anderen User")

    # Hole Dateisystem-Infos
    session_path = session_manager.get_session_by_id(session_id)

    if not session_path:
        raise NotFoundError("Session-Dateien nicht gefunden")

    metadata_path = session_path / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    else:
        metadata = {}

    files = session_manager.get_session_files(session_path)

    return SessionResponse(
        session_id=session_id,
        status=db_session['status'],
        files=files,
        download_all_url=f"/api/download/{session_id}/all",
        created_at=db_session['created_at'],
        progress=metadata.get("progress")
    )


@app.get("/api/session/{session_id}/matches")
async def get_session_matches(
        session_id: str,
        current_user: dict = Depends(get_current_user)
):
    """
    Gibt die kompletten Match-Daten einer Session zurück.
    Inkludiert die korrekten Dateinamen für Downloads.
    """
    user_id = current_user['id']

    db_session = db_get_session_by_id(session_id)
    if not db_session:
        raise NotFoundError("Session nicht gefunden")

    if db_session['user_id'] != user_id:
        raise AuthorizationError("Diese Session gehört einem anderen User")

    session_path = session_manager.get_session_by_id(session_id)
    if not session_path:
        raise NotFoundError("Session nicht gefunden")

    data_file = session_path / "spesen_data.json"
    if not data_file.exists():
        return []

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            matches_data = json.load(f)

        # Gespeicherte Fahrtkosten/OeVM des Users
        expenses_map = {
            (e['heim_team'], e['gast_team'], e['datum']): e
            for e in get_all_match_expenses_for_user(user_id)
        }

        # Füge Dateinamen und Spesen zu jedem Match hinzu
        for match in matches_data:
            filename = generate_filename_from_match(match)
            spiel_info = match.get('spiel_info', {})
            match['_filename'] = filename
            match['_session_id'] = session_id
            match['_pdf_available'] = (session_path / filename).with_suffix('.pdf').exists()
            match['_datum'] = extract_iso_date_from_anpfiff(spiel_info.get('anpfiff', ''))
            match['_expenses'] = expenses_map.get((
                spiel_info.get('heim_team', ''),
                spiel_info.get('gast_team', ''),
                match['_datum'],
            ))
            # Spesen hinzufügen
            _add_spesen_to_match(match)

        return matches_data

    except Exception as e:
        logger.error(f"Fehler beim Laden der Match-Daten: {e}")
        raise APIError(f"Fehler beim Laden der Match-Daten: {str(e)}")


# WICHTIG: ZIP-Download MUSS VOR dem Einzelfile-Download kommen!
# Sonst matched FastAPI /all als filename
@app.get("/api/download/{session_id}/all")
async def download_all_as_zip(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Download aller Dateien einer Session als ZIP.
    WICHTIG: Dieser Endpoint MUSS vor download_file() stehen!
    """
    user_id = current_user['id']

    # Pruefe ob Session dem User gehoert
    db_session = db_get_session_by_id(session_id)

    if not db_session:
        raise NotFoundError("Session nicht gefunden")

    if db_session['user_id'] != user_id:
        raise AuthorizationError("Diese Session gehört einem anderen User")

    logger.info("=" * 80)
    logger.info(f"ZIP-Download START fuer Session: {session_id}")
    logger.info(f"SessionManager base_output_dir: {session_manager.base_output_dir}")

    session_path = session_manager.get_session_by_id(session_id)

    if not session_path:
        logger.error(f"Session nicht gefunden: {session_id}")
        expected_path = session_manager.base_output_dir / session_id
        logger.error(f"Erwarteter Pfad: {expected_path}")
        logger.error(f"Existiert: {expected_path.exists()}")
        raise HTTPException(status_code=404, detail="Session nicht gefunden")

    logger.info(f"Session-Pfad: {session_path}")
    logger.info(f"Existiert: {session_path.exists()}")

    # Liste Dateien auf
    if session_path.exists():
        all_files = list(session_path.iterdir())
        logger.info(f"Dateien im Ordner: {[f.name for f in all_files]}")

    # Finde DOCX-Dateien
    docx_files = list(session_path.glob("*.docx"))
    logger.info(f"Gefundene DOCX-Dateien: {len(docx_files)}")

    if not docx_files:
        logger.error("Keine DOCX-Dateien gefunden!")

        # Pruefe Status
        status = db_session['status']
        logger.error(f"Session-Status: {status}")

        if status in ["pending", "in_progress", "scraping", "generating"]:
            raise HTTPException(
                status_code=425,
                detail=f"Dokumente werden noch erstellt (Status: {status})"
            )
        elif status == "failed":
            raise HTTPException(
                status_code=500,
                detail="Die Dokument-Generierung ist fehlgeschlagen"
            )

        raise HTTPException(status_code=404, detail="Keine DOCX-Dateien gefunden")

    zip_filename = f"spesen_{session_id}.zip"
    zip_path = session_path / zip_filename

    logger.info(f"Erstelle ZIP: {zip_path}")

    try:
        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zipf:
            for docx in docx_files:
                zipf.write(str(docx), docx.name)
                logger.info(f"  Added: {docx.name}")

        if not zip_path.exists():
            raise HTTPException(status_code=500, detail="ZIP-Erstellung fehlgeschlagen")

        zip_size = zip_path.stat().st_size
        logger.info(f"ZIP erstellt: {zip_size} bytes")
        logger.info("=" * 80)

        # Download protokollieren (best-effort, blockiert den Download nie)
        try:
            log_download(user_id, session_id, zip_filename, 'zip')
        except Exception as e:
            logger.error(f"Download-Logging fehlgeschlagen: {e}")

        return FileResponse(
            path=str(zip_path),
            filename=f"spesen_{datetime.now().strftime('%Y%m%d')}.zip",
            media_type="application/zip"
        )

    except Exception as e:
        logger.error(f"ZIP-Fehler: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Erstellen der ZIP: {str(e)}"
        )


@app.get("/api/download/{session_id}/{filename}")
async def download_file(
    session_id: str,
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Download einer einzelnen Datei aus einer Session.
    WICHTIG: Dieser Endpoint MUSS nach download_all_as_zip() stehen!
    """
    user_id = current_user['id']

    # Pruefe ob Session dem User gehoert
    db_session = db_get_session_by_id(session_id)

    if not db_session:
        raise NotFoundError("Session nicht gefunden")

    if db_session['user_id'] != user_id:
        raise AuthorizationError("Diese Session gehört einem anderen User")

    session_path = session_manager.get_session_by_id(session_id)

    if not session_path:
        raise NotFoundError("Session nicht gefunden")

    file_path = session_path / filename

    if not file_path.exists():
        raise NotFoundError("Datei nicht gefunden")

    if filename.endswith('.docx'):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif filename.endswith('.pdf'):
        media_type = "application/pdf"
    elif filename.endswith('.json'):
        media_type = "application/json"
    else:
        media_type = "application/octet-stream"

    # Download protokollieren (best-effort, blockiert den Download nie)
    try:
        file_type = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'unbekannt'
        log_download(user_id, session_id, filename, file_type)
    except Exception as e:
        logger.error(f"Download-Logging fehlgeschlagen: {e}")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type
    )


@app.post("/api/scheduler/trigger")
async def trigger_scheduler_now(current_user: dict = Depends(get_current_user)):
    """
    Triggert die automatische Session-Erstellung sofort (für Admin/Testzwecke).
    Erfordert Authentifizierung.

    ACHTUNG: Startet Session-Erstellung für ALLE User!
    """
    logger.info(f"Manueller Scheduler-Trigger durch User {current_user['email']}")

    scheduler = get_scheduler()

    # Starte in Background Task (nicht blockierend)
    import asyncio
    asyncio.create_task(scheduler.trigger_now())

    return {
        "success": True,
        "message": "Automatische Session-Erstellung wurde gestartet",
        "note": "Die Verarbeitung läuft im Hintergrund und kann einige Minuten dauern"
    }


@app.get("/api/scheduler/status")
async def get_scheduler_status(current_user: dict = Depends(get_current_user)):
    """
    Gibt den Status des Schedulers zurück.
    """
    scheduler = get_scheduler()
    job = scheduler.scheduler.get_job('auto_session_creation')

    if job:
        return {
            "running": scheduler.scheduler.running,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "job_id": job.id,
            "job_name": job.name
        }
    else:
        return {
            "running": scheduler.scheduler.running,
            "next_run": None,
            "job_id": None,
            "job_name": None
        }


@app.get("/api/debug/session/{session_id}")
async def debug_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Debug-Endpoint um Session-Details zu prüfen"""
    session_path = session_manager.get_session_by_id(session_id)

    if not session_path:
        return JSONResponse({
            "error": "Session nicht gefunden",
            "session_id": session_id,
            "base_output_dir": str(session_manager.base_output_dir)
        })

    # Alle Dateien auflisten
    all_files = [f.name for f in session_path.iterdir()] if session_path.exists() else []

    # Metadata laden
    metadata = {}
    metadata_path = session_path / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

    # DOCX-Dateien
    docx_files = [f.name for f in session_path.glob("*.docx")]

    return JSONResponse({
        "session_id": session_id,
        "session_path": str(session_path),
        "session_exists": session_path.exists(),
        "all_files": all_files,
        "docx_files": docx_files,
        "docx_count": len(docx_files),
        "metadata": metadata,
        "base_output_dir": str(session_manager.base_output_dir)
    })


@app.get("/api/health")
async def health_check():
    """Health Check Endpoint"""
    return {
        "status": "online",
        "service": "Spesenfuchs API",
        "version": "1.1.1",
        "output_dir": str(session_manager.base_output_dir)
    }


@app.get("/api/stats/public")
async def get_public_stats():
    """
    Oeffentliche Statistiken fuer die Landingpage (kein Login noetig).
    Zaehlt live die generierten DOCX-Dokumente im Output-Verzeichnis.
    """
    try:
        count = sum(1 for _ in session_manager.base_output_dir.glob("*/*.docx"))
    except Exception as e:
        logger.error(f"Fehler beim Zaehlen der Dokumente: {e}")
        count = 0
    return {"documents_generated": count}


# ===== Frontend Routes =====
@app.get("/")
async def root():
    """Serve Frontend Root"""
    if not FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend not available")

    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    else:
        raise HTTPException(status_code=404, detail="Frontend not found")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """
    Catch-All Route für Frontend (React Router).
    Liefert index.html für alle nicht-API Routen.
    """
    # API-Routen überspringen
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    # Wenn Frontend nicht verfügbar, 404
    if not FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend not available")

    # index.html ausliefern (für React Router)
    index_path = FRONTEND_DIR / "index.html"

    if index_path.exists():
        return FileResponse(str(index_path))
    else:
        raise HTTPException(status_code=404, detail="Frontend not found")