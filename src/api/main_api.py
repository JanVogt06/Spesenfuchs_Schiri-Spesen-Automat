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
import asyncio
import unicodedata
from io import BytesIO
from urllib.parse import quote

from fastapi import FastAPI, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
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
from utils.pdf_converter import convert_docx_files_to_pdf, convert_docx_bytes_to_pdf
from generator.docx_generator import SpesenGenerator
from generator.spesen_calculator import calculate_spesen, format_spesen
from db.scrape_runs import (
    start_run,
    update_run,
    get_latest_run,
    fail_stale_runs,
)
from db.matches import (
    get_matches_for_user,
    get_match,
    set_official_expenses,
    count_distinct_matches,
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

# Vorlagenpfad und Generator fuer den Download-Pfad. Der Generator haelt keinen
# Zustand und braucht kein Ausgabeverzeichnis - er liefert Bytes.
TEMPLATE_PATH = src_path / "data" / "Spesenabrechnung_Vorlage.docx"
document_generator = SpesenGenerator(TEMPLATE_PATH)

# Jede PDF-Konvertierung startet einen eigenen LibreOffice-Prozess mit 150-300 MB.
# Ohne Begrenzung legen ein paar gleichzeitige Downloads den Container lahm.
PDF_MAX_CONCURRENCY = int(os.getenv("PDF_MAX_CONCURRENCY", "2"))
_pdf_semaphore = asyncio.Semaphore(PDF_MAX_CONCURRENCY)

# Obergrenze fuer eine Sammel-ZIP. Reines DOCX kostet ~25 ms pro Dokument,
# die PDF-Konvertierung dominiert mit ein paar Sekunden pro Aufruf.
MAX_BULK_DOWNLOAD = int(os.getenv("MAX_BULK_DOWNLOAD", "50"))

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
        # Stammt das Spiel aus der Datenbank, sind die Saetze dort beim ersten
        # Scrape eingefroren worden. Die Anzeige muss dasselbe zeigen wie das
        # spaeter erzeugte Dokument - sonst weicht die Karte von der
        # Abrechnung ab, sobald sich die Spesenordnung aendert.
        if 'sr_spesen' in match or 'sra_spesen' in match:
            sr_spesen, sra_spesen = match.get('sr_spesen'), match.get('sra_spesen')
        else:
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
    Alle Spiele des Users, direkt aus der Datenbank.

    Frueher wurden dafuer bei jedem Aufruf saemtliche Session-Ordner des Users
    eingelesen und die Spiele ueber (Heim, Gast, Datum) dedupliziert - bei
    knapp 3000 Ordnern der teuerste Endpunkt der Anwendung. Die Deduplizierung
    passiert jetzt schon beim Scrapen ueber den match_key.
    """
    matches = get_matches_for_user(current_user['id'])

    for match in matches:
        _decorate_match(match)

    return matches


def _decorate_match(match: dict) -> dict:
    """Ergaenzt ein Spiel um die Felder, die das Frontend erwartet."""
    match['_id'] = match['id']
    match['_datum'] = match['datum']
    match['_filename'] = generate_filename_from_match(match)
    match['_expenses'] = match.get('expenses')
    match['_missing_since'] = match.get('missing_since')
    _add_spesen_to_match(match)
    return match


class MatchExpensesRequest(BaseModel):
    """Fahrtkosten und OeVM eines Spiels"""
    match_id: int
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
    Speichert Fahrtkosten (km) und OeVM fuer ein Spiel.

    Frueher wurde hier das Dokument sofort neu geschrieben - synchron im
    async-Handler, inklusive LibreOffice-Aufruf. Das entfaellt: Dokumente
    entstehen erst beim Download und tragen den Wert dann automatisch.
    """
    user_id = current_user['id']
    match = _owned_match(request.match_id, user_id)

    # Nur die Felder anfassen, die der Client wirklich geschickt hat. Wuerden
    # fehlende Felder aus den Pydantic-Defaults als None aufgefuellt, loeschte
    # ein Teil-Update die Werte der anderen Rollen mit. Ein ausdruecklich als
    # null gesendetes Feld leert den Eintrag dagegen weiterhin.
    expense_keys = ['sr_km', 'sr_oevm', 'sra1_km', 'sra1_oevm', 'sra2_km', 'sra2_oevm']
    expenses = {}
    for key in expense_keys:
        if key not in request.model_fields_set:
            continue
        value = getattr(request, key)
        if value is not None and (value < 0 or value > 99999):
            raise HTTPException(status_code=400, detail=f"Ungueltiger Wert fuer {key}")
        expenses[key] = value

    set_official_expenses(match['id'], expenses)
    aktualisiert = _decorate_match(get_match(match['id']))

    return {
        "success": True,
        "filename": aktualisiert['_filename'],
        "expenses": aktualisiert['_expenses'],
        "spesen": aktualisiert['_spesen'],
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


# ===== Download-Endpunkte: Dokumente entstehen bei jedem Abruf neu =====

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _content_disposition(filename: str) -> Dict[str, str]:
    """
    Baut den Content-Disposition-Header fuer einen Dateinamen.

    Vereinsnamen enthalten Umlaute und Sonderzeichen ("FSV Preußen"), HTTP-Header
    sind aber auf latin-1 begrenzt - ein roher UTF-8-Name kommt verstuemmelt an
    oder laesst den Response beim Kodieren scheitern. Also ASCII-Variante als
    Rueckfallebene plus filename* nach RFC 5987, das jeder aktuelle Browser
    bevorzugt.
    """
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace('"', "") or "Spesenabrechnung"
    quoted = quote(filename, safe="")

    return {"Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'}


def _owned_match(match_id: int, user_id: int) -> dict:
    """Laedt ein Spiel und stellt sicher, dass es dem User gehoert."""
    match = get_match(match_id)

    if not match:
        raise NotFoundError("Spiel nicht gefunden")

    if match['user_id'] != user_id:
        raise AuthorizationError("Dieses Spiel gehört einem anderen User")

    return match


def _render_docx(match: dict) -> tuple:
    """Rendert ein Spiel zu (Dateiname, DOCX-Bytes)."""
    filename = generate_filename_from_match(match)
    content = document_generator.render_document(match, expenses=match.get('expenses'))
    return filename, content


async def _render_pdfs(documents: List[tuple]) -> Dict[str, bytes]:
    """
    Konvertiert gerenderte DOCX zu PDF.

    Zwei Dinge sind hier wesentlich: die Konvertierung laeuft in einem Thread,
    weil sie sekundenlang blockiert und sonst den kompletten Event-Loop
    anhaelt, und sie laeuft nur begrenzt nebenlaeufig, weil jeder Aufruf einen
    eigenen LibreOffice-Prozess startet.
    """
    async with _pdf_semaphore:
        return await run_in_threadpool(convert_docx_bytes_to_pdf, documents)


@app.get("/api/matches/{match_id}/download/{file_format}")
async def download_match_document(
    match_id: int,
    file_format: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Erzeugt die Abrechnung eines Spiels und liefert sie aus - ohne dass
    jemals eine Datei auf der Platte entsteht.
    """
    if file_format not in ("docx", "pdf"):
        raise APIError(400, "INVALID_FORMAT", "Format muss docx oder pdf sein")

    user_id = current_user['id']
    match = _owned_match(match_id, user_id)

    filename, docx_bytes = await run_in_threadpool(_render_docx, match)

    if file_format == "docx":
        log_download(user_id, filename, "docx", match_id=match_id)
        return Response(
            content=docx_bytes,
            media_type=DOCX_MIME,
            headers=_content_disposition(filename),
        )

    pdfs = await _render_pdfs([(filename, docx_bytes)])
    pdf_bytes = pdfs.get(filename)

    if not pdf_bytes:
        raise APIError(503, "PDF_CONVERSION_FAILED",
                       "Die PDF-Erzeugung ist fehlgeschlagen. Bitte erneut versuchen "
                       "oder das Word-Dokument herunterladen.")

    pdf_filename = filename.replace(".docx", ".pdf")
    log_download(user_id, pdf_filename, "pdf", match_id=match_id)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_content_disposition(pdf_filename),
    )


class BulkDownloadRequest(BaseModel):
    """Auswahl fuer den Sammel-Download"""
    match_ids: List[int]
    file_format: str = "both"


@app.post("/api/matches/download")
async def download_matches_as_zip(
    request: BulkDownloadRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Packt die ausgewaehlten Spiele in ein ZIP - im Speicher, ohne Zwischenablage
    auf der Platte. Loest den alten Session-ZIP-Download ab, der immer "alles
    aus diesem Lauf" war und nie PDFs enthielt.
    """
    if request.file_format not in ("docx", "pdf", "both"):
        raise APIError(400, "INVALID_FORMAT", "Format muss docx, pdf oder both sein")

    if not request.match_ids:
        raise APIError(400, "NO_SELECTION", "Es wurde kein Spiel ausgewählt")

    if len(request.match_ids) > MAX_BULK_DOWNLOAD:
        raise APIError(400, "TOO_MANY_MATCHES",
                       f"Bitte höchstens {MAX_BULK_DOWNLOAD} Spiele auf einmal auswählen")

    user_id = current_user['id']
    matches = [_owned_match(match_id, user_id) for match_id in request.match_ids]

    documents = await run_in_threadpool(lambda: [_render_docx(m) for m in matches])

    pdfs = {}
    if request.file_format in ("pdf", "both"):
        pdfs = await _render_pdfs(documents)
        if not pdfs:
            raise APIError(503, "PDF_CONVERSION_FAILED",
                           "Die PDF-Erzeugung ist fehlgeschlagen. Bitte erneut versuchen "
                           "oder die Word-Dokumente herunterladen.")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in documents:
            if request.file_format in ("docx", "both"):
                archive.writestr(filename, content)

            pdf_bytes = pdfs.get(filename)
            if pdf_bytes:
                archive.writestr(filename.replace(".docx", ".pdf"), pdf_bytes)

    zip_name = f"Spesen_{datetime.now().strftime('%Y-%m-%d')}.zip"

    for match, (filename, _) in zip(matches, documents):
        log_download(user_id, filename, request.file_format, match_id=match['id'])

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers=_content_disposition(zip_name),
    )


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
            log_download(user_id, zip_filename, 'zip', session_id=session_id)
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
        log_download(user_id, filename, file_type, session_id=session_id)
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
    Oeffentliche Statistik fuer die Landingpage (kein Login noetig).

    Gezaehlt werden jetzt verschiedene SPIELE, nicht Dateien auf der Platte.
    Die alte Zahl war die Anzahl aller je geschriebenen DOCX - durch die
    naechtlichen Laeufe lag dieselbe Abrechnung dort rund 19-mal. Ein Spiel,
    das mehrere Unparteiische aus der Nutzerbasis leiten, zaehlt ebenfalls
    nur einmal: der match_key ist userunabhaengig.
    """
    try:
        count = count_distinct_matches()
    except Exception as e:
        logger.error(f"Fehler beim Zaehlen der Spiele: {e}")
        count = 0
    return {"matches_total": count}


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