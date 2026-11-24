"""
FastAPI backend for Spesenfuchs
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

# Load .env before importing modules that read secrets at import time
from core import config
from core.config import load_environment

load_environment()

from scheduler import get_scheduler
from main import scrape_matches
from utils.logger import setup_logger
from utils.match_utils import generate_filename_from_match
from utils.pdf_converter import convert_docx_bytes_to_pdf
from generator.docx_generator import SpesenGenerator
from generator.nofv_generator import NofvGenerator
from db.ligen import alle_staffeln, bestand, tabelle
from utils.mailer import empfaenger, ist_konfiguriert, sende_bug_report
from generator.spesen_calculator import (
    FREUNDSCHAFTSSPIEL,
    POKALSPIEL,
    PUNKTSPIEL,
    calculate_spesen,
    format_spesen,
    ist_nofv_spiel,
    wettbewerbsart,
)
from db.scrape_runs import (
    start_run,
    update_run,
    get_latest_run,
    has_active_run,
    fail_stale_runs,
)
from db.matches import (
    get_matches_for_user,
    get_match,
    set_official_expenses,
    count_distinct_matches,
)
from db.database import (
    dfb_login_abgelehnt,
    init_database,
    log_download,
    log_spielbericht,
)
from db.stammdaten import get_stammdaten
from utils.geocoder import geocode, GeocoderNichtErreichbar
from utils.fahrten import vorschlaege_fuer_spiel
from utils.statistik import statistik
from utils.spielstaetten import besuchte_spielstaetten
from db.season import get_saisons, get_saison
from db.beobachtungen import get_beobachtungen
from db.spielberichte import get_bericht, get_dokument, get_index, Zuordnung, kurzinfo
from api.auth import router as auth_router, get_current_user
from core.errors import (
    APIError,
    NotFoundError,
    CredentialsMissingError,
    ValidationError,
    api_error_handler,
    generic_exception_handler,
    DFBCredentialsInvalidError
)

logger = setup_logger("api")

# Important for multiprocessing on Windows
multiprocessing.freeze_support()


# ===== Lifespan context manager (replaces deprecated on_event) =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    Replaces the deprecated @app.on_event decorators.
    """
    # === STARTUP ===
    init_database()
    logger.info("Datenbank initialisiert")

    # Finish runs that the last process could not complete (restart, crash),
    # otherwise the frontend keeps polling a dead run forever
    fail_stale_runs()

    # Start the scheduler
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("Automatischer Session-Scheduler gestartet")

    yield  # app runs here

    # === SHUTDOWN ===
    scheduler = get_scheduler()
    scheduler.stop()
    logger.info("Scheduler gestoppt")


app = FastAPI(title="Spesenfuchs API", lifespan=lifespan)

# Register exception handlers
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://spesen-generator.jan-vogt.dev",
        "http://localhost:5173",  # for local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Frontend static files (for Docker production) =====
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", "./frontend/dist"))

if FRONTEND_DIR.exists():
    # Static assets (CSS, JS, images)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
    logger.info(f"Frontend wird ausgeliefert von: {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend-Verzeichnis nicht gefunden: {FRONTEND_DIR}")

# Add after the /assets mount:
@app.get("/appicon.png")
async def serve_favicon():
    """Serve App Icon"""
    icon_path = FRONTEND_DIR / "appicon.png"
    if icon_path.exists():
        return FileResponse(str(icon_path), media_type="image/png")
    raise HTTPException(status_code=404, detail="Icon not found")

# Template path and generator for the download path. The generator keeps no
# state and needs no output directory - it returns bytes.
TEMPLATE_PATH = src_path / "data" / "Spesenabrechnung_Vorlage.docx"
document_generator = SpesenGenerator(TEMPLATE_PATH)

# NOFV mandatory (Pflicht) matches have their own form: an Excel workbook with
# one receipt per referee, three pages as a PDF.
NOFV_TEMPLATE_PATH = src_path / "data" / "SR-Reisekostenabrechnung_NOFV.xlsx"
nofv_generator = NofvGenerator(NOFV_TEMPLATE_PATH)

# Every PDF conversion starts its own LibreOffice process of 150-300 MB.
# Without a limit, a few concurrent downloads bring the container to a halt.
PDF_MAX_CONCURRENCY = int(os.getenv("PDF_MAX_CONCURRENCY", "2"))
_pdf_semaphore = asyncio.Semaphore(PDF_MAX_CONCURRENCY)

# Upper limit for a bulk ZIP. Plain DOCX costs ~25 ms per document,
# the PDF conversion dominates with a few seconds per call.
MAX_BULK_DOWNLOAD = int(os.getenv("MAX_BULK_DOWNLOAD", "50"))

app.include_router(auth_router)

# Running background tasks (see trigger_scheduler)
_hintergrund_tasks: set = set()


# ===== Request/Response Models =====

class GenerateRequest(BaseModel):
    """Request for expense generation"""
    pass  # Credentials are loaded from the user profile


# ===== Helper Functions =====

def _add_spesen_to_match(match: dict) -> dict:
    """
    Adds computed expense information to a match.

    Computes referee (SR) and assistant referee (SRA) expenses based on the Spielklasse (league level)
    and team type and adds them to the match as a _spesen object.

    Args:
            match: Match dictionary with spiel_info and schiedsrichter

    Returns:
            Match with the added _spesen object
    """
    spiel_info = match.get('spiel_info', {})
    schiedsrichter = match.get('schiedsrichter', [])

    spielklasse = spiel_info.get('spielklasse', '')
    mannschaftsart = spiel_info.get('mannschaftsart', '')
    art = wettbewerbsart(spielklasse)

    # If the match comes from the database, the rates were frozen there at the
    # first scrape. The display must show the same as the document generated
    # later - otherwise the card deviates from the settlement as soon as the
    # expense regulations change.
    if 'sr_spesen' in match or 'sra_spesen' in match:
        sr_spesen, sra_spesen = match.get('sr_spesen'), match.get('sra_spesen')
    else:
        sr_spesen, sra_spesen = calculate_spesen(
            spielklasse, mannschaftsart, spiel_info.get('staffel', ''),
            spiel_info.get('heim_team', ''), spiel_info.get('gast_team', '')
        )

    spesen_info = {
        'sr': sr_spesen,
        'sra': sra_spesen,
        'sr_formatted': format_spesen(sr_spesen),
        'sra_formatted': format_spesen(sra_spesen),
        'is_punktspiel': art == PUNKTSPIEL,
        'sra_count': sum(1 for sr in schiedsrichter if sr.get('rolle', '').startswith('SRA')),
        'hinweis': None,
    }

    # Without a rate a reason belongs with it, otherwise the referee faces an
    # empty field and does not know whether the application overlooked something
    # or whether there is nothing to calculate here.
    if sr_spesen is None:
        if art == POKALSPIEL:
            spesen_info['hinweis'] = (
                'Pokalspiel: der Satz richtet sich nach der höchstklassigen beteiligten '
                'Mannschaft (§2 Abs. 3) und lässt sich aus der Ansetzung nicht ableiten'
            )
        elif art == FREUNDSCHAFTSSPIEL:
            spesen_info['hinweis'] = (
                'Freundschaftsspiel: der Satz richtet sich nach der aktuellen Spielklasse '
                'des Gastgebers (§2 Abs. 4) und lässt sich aus der Ansetzung nicht ableiten'
            )
        else:
            spesen_info['hinweis'] = (
                'Spesen konnten nicht automatisch ermittelt werden '
                '(überregionales Spiel oder unbekannte Spielklasse)'
            )

    match['_spesen'] = spesen_info
    return match


# ===== Scrape process =====

def run_scrape_process(dfb_username: str, dfb_password: str, user_id: int, run_id: int):
    """
    Runs the scrape in its own process.

    The separate process is needed because Playwright cannot run inside the
    API's asyncio loop. Progress flows back through the scrape_runs table -
    it used to be a metadata.json in the session folder.

    Documents are no longer generated here: they are created on download.
    """
    from utils.logger import setup_logger
    from core.errors import DFBCredentialsInvalidError

    process_logger = setup_logger("scrape_process")

    try:
        process_logger.info(f"[User {user_id}] Starte Scrape")
        update_run(run_id, status="scraping", step="Scraping gestartet...")

        def fortschritt(current, total, step):
            update_run(run_id, status="scraping", step=step, current=current, total=total)

        matches = scrape_matches(
            username=dfb_username,
            password=dfb_password,
            user_id=user_id,
            progress_callback=fortschritt,
        )

        anzahl = len(matches)
        update_run(
            run_id,
            status="completed",
            step="Fertig!" if anzahl else "Keine Spiele gefunden",
            current=anzahl,
            total=anzahl,
            matches_found=anzahl,
            finished=True,
        )
        process_logger.info(f"[User {user_id}] Scrape abgeschlossen: {anzahl} Spiele")

    except DFBCredentialsInvalidError as e:
        process_logger.error(f"[User {user_id}] DFB-Login fehlgeschlagen: {e.message}")
        update_run(
            run_id,
            status="failed",
            step="Fehler",
            error_code="DFB_CREDENTIALS_INVALID",
            error_message="Die DFBnet-Zugangsdaten sind ungültig. Bitte prüfe Benutzername "
                          "und Passwort in den Einstellungen.",
            finished=True,
        )
        # Only after the run: if this write fails, the run should
        # still show up as failed.
        dfb_login_abgelehnt(user_id)

    except Exception as e:
        process_logger.error(f"[User {user_id}] Fehler beim Scrape: {e}", exc_info=True)
        update_run(
            run_id,
            status="failed",
            step="Fehler",
            error_code="GENERATION_ERROR",
            error_message="Beim Abrufen der Spiele ist ein Fehler aufgetreten.",
            finished=True,
        )


@app.post("/api/generate")
async def generate_spesen(
    request: GenerateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Starts a new fetch of the assignments (Ansetzungen).

    No folder and no file is created any more - only a row in
    scrape_runs, which the frontend polls, and afterwards matches in the database.
    """
    user_id = current_user['id']
    logger.info(f"[User {user_id}] startet Abruf")

    from db.database import get_dfb_credentials
    from core.encryption import decrypt_credential

    dfb_creds = get_dfb_credentials(user_id)
    if not dfb_creds:
        raise CredentialsMissingError()

    dfb_username = decrypt_credential(dfb_creds['dfb_username_encrypted'])
    dfb_password = decrypt_credential(dfb_creds['dfb_password_encrypted'])

    # Clean up runs whose process has died beforehand - otherwise the
    # frontend poll stays stuck on the old run
    fail_stale_runs()

    # A second run for the same user would be a second Playwright process with
    # the same DFBnet login, and the poll would no longer know which run it is
    # showing. Double click or a collision with the nightly job.
    if has_active_run(user_id):
        raise APIError(409, "RUN_ALREADY_ACTIVE",
                       "Es läuft bereits ein Abruf. Bitte warte, bis er fertig ist.")

    run_id = start_run(user_id)

    # Credentials are passed directly as a parameter (not via ENV!)
    process = multiprocessing.Process(
        target=run_scrape_process,
        args=(dfb_username, dfb_password, user_id, run_id),
        daemon=True
    )
    process.start()

    return {
        "run_id": run_id,
        "status": "pending",
        "progress": {"current": 0, "total": 0, "step": "Starte..."},
    }


@app.get("/api/scrape/status")
async def get_scrape_status(current_user: dict = Depends(get_current_user)):
    """
    Current state of the most recent scrape run. Replaces the poll on the
    session metadata.

    error_code still carries DFB_CREDENTIALS_INVALID so that the frontend
    can send the user to the settings as before.
    """
    # Clean up crashed runs so the poll does not stay on
    # "scraping" forever
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


@app.get("/api/matches")
async def get_all_user_matches(current_user: dict = Depends(get_current_user)):
    """
    All matches of the user, straight from the database.

    It used to read all of the user's session folders on every call
    and deduplicate the matches by (home, away, date) - with
    almost 3000 folders the most expensive endpoint of the application. The
    deduplication now already happens during scraping via the match_key.
    """
    matches = get_matches_for_user(current_user['id'])
    zuordnung = Zuordnung(get_index(current_user['id']))

    for match in matches:
        _decorate_match(match)
        info = match.get('spiel_info') or {}
        # A withdrawn match was not refereed - it has no report
        match['_spielbericht'] = None if match.get('missing_since') else kurzinfo(zuordnung.finde(
            match.get('datum') or '', info.get('heim_team') or '', info.get('gast_team') or '',
            info.get('anpfiff') or '',
        ))

    return matches


def _decorate_match(match: dict) -> dict:
    """Adds the fields the frontend expects to a match."""
    match['_id'] = match['id']
    match['_datum'] = match['datum']
    match['_filename'] = generate_filename_from_match(match)
    match['_expenses'] = match.get('expenses')
    match['_missing_since'] = match.get('missing_since')
    _add_spesen_to_match(match)
    return match


class MatchExpensesRequest(BaseModel):
    """Travel costs and public transport (OeVM) of a match"""
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
    Stores travel costs (km) and public transport (OeVM) for a match.

    It used to rewrite the document immediately here - synchronously in the
    async handler, including the LibreOffice call. That is gone: documents
    are only created on download and then pick up the value automatically.
    """
    user_id = current_user['id']
    match = _owned_match(request.match_id, user_id)

    # Only touch the fields the client actually sent. If missing fields were
    # filled in as None from the Pydantic defaults, a partial update would also
    # wipe the values of the other roles. A field explicitly sent as
    # null, however, still clears the entry.
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


# ===== Map: addresses of the assigned officials and the venue =====

# Tile source of the map. The default is the standard style of
# OpenStreetMap; anyone serving their own tiles sets both to match. The
# value goes to the browser, not to the server - the map loads the
# tiles itself.
MAP_TILE_URL = os.getenv(
    "MAP_TILE_URL",
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
)
MAP_TILE_ATTRIBUTION = os.getenv(
    "MAP_TILE_ATTRIBUTION",
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
)


def _geo_eintraege(match: dict) -> List[dict]:
    """The addresses of a match in the order in which they should go on the map."""
    eintraege = []

    spielstaette = match.get("spielstaette") or {}
    if spielstaette.get("adresse"):
        eintraege.append({
            "typ": "spielstaette",
            "rolle": "Spielort",
            "name": spielstaette.get("name") or "Spielstätte",
            "adresse": spielstaette["adresse"],
            "ort": None,
        })

    for person in match.get("schiedsrichter") or []:
        # Only occupied roles with a usable address. A bare
        # street without a town would be ambiguous across all of Germany.
        if not person.get("name") or not person.get("plz_ort"):
            continue

        strasse = (person.get("strasse") or "").strip()
        plz_ort = person["plz_ort"].strip()
        eintraege.append({
            "typ": "person",
            "rolle": person.get("rolle") or "Unparteiischer",
            "name": person["name"],
            "adresse": f"{strasse}, {plz_ort}" if strasse else plz_ort,
            "ort": plz_ort,
        })

    return eintraege


def _build_geo(match: dict) -> dict:
    """
    Resolves the addresses of a match to coordinates.

    Two people at the same address (family on the same crew is
    not unusual) would lie on top of each other as two pins and hide
    each other. They are therefore merged into one point that names both
    roles.
    """
    punkte: List[dict] = []
    ohne_treffer: List[dict] = []
    nach_koordinate: Dict[tuple, dict] = {}
    gestoert = False

    for eintrag in _geo_eintraege(match):
        try:
            treffer = geocode(eintrag["adresse"], eintrag["ort"])
        except GeocoderNichtErreichbar:
            gestoert = True
            treffer = None

        if not treffer:
            ohne_treffer.append({
                "rolle": eintrag["rolle"],
                "name": eintrag["name"],
                "adresse": eintrag["adresse"],
            })
            continue

        # Round to about eleven metres: closer together, two pins cannot be
        # told apart at any sensible zoom.
        schluessel = (round(treffer["lat"], 4), round(treffer["lon"], 4))
        vorhanden = nach_koordinate.get(schluessel)

        if vorhanden:
            vorhanden["eintraege"].append({"rolle": eintrag["rolle"], "name": eintrag["name"]})
            continue

        punkt = {
            "typ": eintrag["typ"],
            "adresse": eintrag["adresse"],
            "lat": treffer["lat"],
            "lon": treffer["lon"],
            "genauigkeit": treffer["genauigkeit"],
            "eintraege": [{"rolle": eintrag["rolle"], "name": eintrag["name"]}],
        }
        nach_koordinate[schluessel] = punkt
        punkte.append(punkt)

    return {
        "punkte": punkte,
        "ohne_treffer": ohne_treffer,
        "gestoert": gestoert,
        "kacheln": {"url": MAP_TILE_URL, "attribution": MAP_TILE_ATTRIBUTION},
    }


@app.get("/api/matches/{match_id}/geo")
async def get_match_geo(match_id: int, current_user: dict = Depends(get_current_user)):
    """
    The addresses of a match as coordinates for the map.

    Runs in the thread pool: the first call for a match asks the geocoder for up to four
    addresses, and it keeps a minimum gap between
    requests. From the second call on everything comes from the database.
    """
    match = _owned_match(match_id, current_user['id'])
    return await run_in_threadpool(_build_geo, match)


@app.get("/api/matches/{match_id}/fahrten")
async def get_match_fahrten(match_id: int, current_user: dict = Depends(get_current_user)):
    """
    Kilometre suggestions for a match: each person alone and as a
    carpool. Like the map, in the thread pool - the first call queries
    the address search and the route planner, afterwards everything comes from the database.
    """
    match = _owned_match(match_id, current_user['id'])
    return await run_in_threadpool(vorschlaege_fuer_spiel, match)


@app.get("/api/statistik")
async def get_statistik(saison: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """
    Expenses and travel costs of the user's own past matches of a season.

    Estimated travel costs need the address search and the route planner. Whatever
    could not be looked up within a few seconds is reported as "offen" (open) -
    the frontend then asks again and gets the rest.
    """
    return await run_in_threadpool(statistik, current_user['id'], saison)


@app.get("/api/spielstaetten")
async def get_spielstaetten(current_user: dict = Depends(get_current_user)):
    """
    The venues where the user has already been on duty, for the map in the
    Saison tab. Like the statistics: whatever could not be looked up quickly is in
    "offen" (open), and the frontend asks again.
    """
    daten = await run_in_threadpool(besuchte_spielstaetten, current_user['id'])
    return {**daten, "kacheln": {"url": MAP_TILE_URL, "attribution": MAP_TILE_ATTRIBUTION}}


# ===== Download endpoints: documents are created anew on every request =====

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# "docx" is the historical name for "the editable file" - for
# NOFV matches this is an Excel workbook. Both names mean the same thing.
BEARBEITBARE_FORMATE = ("docx", "xlsx")


def _mime_fuer(filename: str) -> str:
    return XLSX_MIME if filename.endswith(".xlsx") else DOCX_MIME


def _pdf_name(filename: str) -> str:
    """Spesen_A_vs_B.docx / .xlsx -> Spesen_A_vs_B.pdf"""
    return str(Path(filename).with_suffix(".pdf"))


def _content_disposition(filename: str) -> Dict[str, str]:
    """
    Builds the Content-Disposition header for a file name.

    Club names contain umlauts and special characters ("FSV Preußen"), but HTTP headers
    are limited to latin-1 - a raw UTF-8 name arrives garbled
    or makes the response fail while encoding. So an ASCII variant as the
    fallback plus filename* per RFC 5987, which every current browser
    prefers.
    """
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace('"', "") or "Spesenabrechnung"
    quoted = quote(filename, safe="")

    return {"Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'}


def _owned_match(match_id: int, user_id: int) -> dict:
    """Loads a match and makes sure it belongs to the user."""
    match = get_match(match_id)

    if not match:
        raise NotFoundError("Spiel nicht gefunden")

    # Treat it like a missing match: a 403 would reveal that the ID exists.
    # Match reports do the same.
    if match['user_id'] != user_id:
        raise NotFoundError("Spiel nicht gefunden")

    return match


def _render_dokument(match: dict) -> tuple:
    """
    Renders a match to (file name, bytes) - DOCX for the TFV form,
    XLSX for the NOFV receipt. The file name extension tells which.
    """
    filename = generate_filename_from_match(match)

    if ist_nofv_spiel(match.get('spiel_info', {})):
        content = nofv_generator.render_workbook(match, expenses=match.get('expenses'))
    else:
        content = document_generator.render_document(match, expenses=match.get('expenses'))

    return filename, content


async def _render_pdfs(documents: List[tuple]) -> List[Optional[bytes]]:
    """
    Converts rendered DOCX/XLSX to PDF.

    Two things are essential here: the conversion runs in a thread,
    because it blocks for seconds and would otherwise halt the entire event loop,
    and it runs only with limited concurrency, because every call starts a
    separate LibreOffice process.
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
    Generates the settlement of a match and delivers it - without
    a file ever being created on disk.
    """
    if file_format not in (*BEARBEITBARE_FORMATE, "pdf"):
        raise APIError(400, "INVALID_FORMAT", "Format muss docx, xlsx oder pdf sein")

    user_id = current_user['id']
    match = _owned_match(match_id, user_id)

    filename, content = await run_in_threadpool(_render_dokument, match)

    if file_format in BEARBEITBARE_FORMATE:
        log_download(user_id, filename, Path(filename).suffix.lstrip("."), match_id=match_id)
        return Response(
            content=content,
            media_type=_mime_fuer(filename),
            headers=_content_disposition(filename),
        )

    pdf_bytes = (await _render_pdfs([(filename, content)]))[0]

    if not pdf_bytes:
        raise APIError(503, "PDF_CONVERSION_FAILED",
                       "Die PDF-Erzeugung ist fehlgeschlagen. Bitte erneut versuchen "
                       "oder das bearbeitbare Dokument herunterladen.")

    pdf_filename = _pdf_name(filename)
    log_download(user_id, pdf_filename, "pdf", match_id=match_id)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_content_disposition(pdf_filename),
    )


class BulkDownloadRequest(BaseModel):
    """Selection for the bulk download"""
    match_ids: List[int]
    file_format: str = "both"


@app.post("/api/matches/download")
async def download_matches_as_zip(
    request: BulkDownloadRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Packs the selected matches into a ZIP - in memory, without an intermediate
    file on disk. Replaces the old session ZIP download, which was always "everything
    from this run" and never contained PDFs.
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

    documents = await run_in_threadpool(lambda: [_render_dokument(m) for m in matches])

    pdfs: List[Optional[bytes]] = [None] * len(documents)
    if request.file_format in ("pdf", "both"):
        pdfs = await _render_pdfs(documents)

        # A PARTIAL failure is also an error. Missing PDFs used to be
        # skipped silently and the user got an HTTP 200 with an
        # incomplete archive without noticing.
        fehlend = sum(1 for pdf in pdfs if pdf is None)
        if fehlend:
            raise APIError(503, "PDF_CONVERSION_FAILED",
                           f"Für {fehlend} von {len(documents)} Spielen konnte keine PDF "
                           "erzeugt werden. Bitte erneut versuchen oder die bearbeitbaren "
                           "Dokumente herunterladen.")

    buffer = BytesIO()
    # Identical file names are possible (two tournaments on the same day), so
    # every entry gets a suffix if necessary - otherwise the archive would
    # contain two files of the same name.
    vergeben: Dict[str, int] = {}

    def eindeutig(name: str) -> str:
        if name not in vergeben:
            vergeben[name] = 1
            return name
        vergeben[name] += 1
        stamm, _, endung = name.rpartition(".")
        return f"{stamm} ({vergeben[name]}).{endung}"

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for (filename, content), pdf_bytes in zip(documents, pdfs):
            basis = eindeutig(filename)

            if request.file_format in ("docx", "both"):
                archive.writestr(basis, content)

            if pdf_bytes:
                archive.writestr(_pdf_name(basis), pdf_bytes)

    zip_name = f"Spesen_{datetime.now().strftime('%Y-%m-%d')}.zip"

    for match, (filename, _) in zip(matches, documents):
        # As with the single download: whoever only fetches PDFs got the PDF
        name = _pdf_name(filename) if request.file_format == "pdf" else filename
        log_download(user_id, name, request.file_format, match_id=match['id'])

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers=_content_disposition(zip_name),
    )


@app.post("/api/scheduler/trigger")
async def trigger_scheduler_now(current_user: dict = Depends(get_current_user)):
    """
    Starts the nightly fetch immediately (for test purposes).

    WARNING: affects ALL users - the run decrypts the DFBnet credentials
    of every account and logs in with them. This project has
    no roles, so the endpoint was open to every registered user.
    It is therefore disabled by default and must be enabled via the
    environment.
    """
    if os.getenv("ALLOW_SCHEDULER_TRIGGER", "").lower() not in ("1", "true", "yes"):
        raise APIError(403, "TRIGGER_DISABLED",
                       "Der manuelle Sammel-Abruf ist abgeschaltet. "
                       "Zum Freigeben ALLOW_SCHEDULER_TRIGGER=1 setzen.")

    logger.warning(f"Manueller Scheduler-Trigger durch User {current_user['id']}")

    scheduler = get_scheduler()
    task = asyncio.create_task(scheduler.scrape_all_users())
    # asyncio keeps only a weak reference - without this one the
    # garbage collector could clean up the run midway.
    _hintergrund_tasks.add(task)
    task.add_done_callback(_hintergrund_tasks.discard)

    return {
        "success": True,
        "message": "Automatischer Abruf wurde gestartet",
        "note": "Die Verarbeitung läuft im Hintergrund und kann einige Minuten dauern"
    }


@app.get("/api/scheduler/status")
async def get_scheduler_status(current_user: dict = Depends(get_current_user)):
    """Status of the nightly fetch"""
    return get_scheduler().get_status()


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Spesenfuchs API",
        "version": config.APP_VERSION,
        "matches": count_distinct_matches()
    }


@app.get("/api/stats/public")
async def get_public_stats():
    """
    Public statistics for the landing page (no login required).

    Now counts distinct MATCHES, not files on disk.
    The old number was the count of all DOCX ever written - because of the
    nightly runs the same settlement was in there about 19 times. A match
    refereed by several officials from the user base also counts
    only once: the match_key is user-independent.
    """
    try:
        count = count_distinct_matches()
    except Exception as e:
        logger.error(f"Fehler beim Zaehlen der Spiele: {e}")
        count = 0
    return {"matches_total": count}



@app.get("/api/stammdaten")
async def get_own_stammdaten(current_user: dict = Depends(get_current_user)):
    """
    The logged-in user's own master data (Stammdaten) from DFBnet.

    Before the first fetch this deliberately returns 200 with null and not a 404 or
    401: the interceptor in the frontend throws the user hard onto
    the login page on every 401, and "nothing fetched yet" is an empty state, not an
    error.

    A scoping check like _owned_match is not needed - the table's key
    IS the user_id.
    """
    return get_stammdaten(current_user['id'])


@app.get("/api/saison")
async def get_own_saisons(current_user: dict = Depends(get_current_user)):
    """
    The seasons for which refereed matches are stored - newest first.

    An empty list before the first fetch, not an error: the tab then shows
    its empty state.
    """
    return get_saisons(current_user['id'])


@app.get("/api/saison/{saison:path}")
async def get_own_saison(saison: str, current_user: dict = Depends(get_current_user)):
    """
    One season with all refereed matches, assignment balance and courses (Lehrgaenge).

    The path parameter is declared as :path because season names at DFBnet
    contain a slash ("26/27"). Without that the route would end after
    the 26 and the rest would be a path segment of its own.
    """
    daten = get_saison(current_user['id'], saison)

    if not daten:
        raise NotFoundError(f"Zur Saison {saison} ist nichts gespeichert")

    zuordnung = Zuordnung(get_index(current_user['id']))
    for spiel in daten['spiele']:
        spiel['spielbericht'] = kurzinfo(zuordnung.finde(
            spiel['datum'], spiel['heim'], spiel['gast'], spiel.get('uhrzeit') or ''
        ))

    return daten


# Allowed values for the log. Whatever else the frontend sends becomes "direkt" -
# no free text from outside goes into the table.
_BERICHT_QUELLEN = {"saison", "spesen"}
_DOKUMENT_AKTIONEN = {"oeffnen": "dokument_oeffnen", "laden": "dokument_laden"}


def _log_spielbericht(user_id: int, bericht_id: int, aktion: str, quelle: str = "direkt",
                      dokument_id: Optional[int] = None) -> None:
    """An error in the log must not prevent the report - just log it."""
    try:
        log_spielbericht(user_id, bericht_id, aktion, quelle, dokument_id)
    except Exception as e:
        logger.warning(f"Spielbericht-Log nicht geschrieben: {e}")


@app.get("/api/spielberichte/{bericht_id}")
async def get_own_spielbericht(
    bericht_id: int,
    quelle: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    A match report (Spielbericht) with match progression, line-ups, crew costs and the
    list of attached documents.

    Scoped via the user_id in the query - someone else's report is
    simply "not found".
    """
    bericht = get_bericht(current_user['id'], bericht_id)

    if not bericht:
        raise NotFoundError("Spielbericht nicht gefunden")

    _log_spielbericht(current_user['id'], bericht_id, "ansehen",
                      quelle if quelle in _BERICHT_QUELLEN else "direkt")
    return bericht


@app.get("/api/spielberichte/{bericht_id}/dokumente/{dokument_id}")
async def download_spielbericht_dokument(
    bericht_id: int,
    dokument_id: int,
    aktion: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """A document attached to the match report (special report, expense document, ...)."""
    dokument = get_dokument(current_user['id'], bericht_id, dokument_id)

    if not dokument or not dokument['absolut'].is_file():
        raise NotFoundError("Dokument nicht gefunden")

    _log_spielbericht(current_user['id'], bericht_id,
                      _DOKUMENT_AKTIONEN.get(aktion or "", "dokument_laden"), "bericht", dokument_id)

    dateiname = dokument['dateiname']
    media_type = "application/pdf" if dateiname.lower().endswith(".pdf") else "application/octet-stream"

    return FileResponse(
        str(dokument['absolut']),
        media_type=media_type,
        headers=_content_disposition(dateiname),
    )

@app.get("/api/beobachtungen")
async def get_own_beobachtungen(current_user: dict = Depends(get_current_user)):
    """
    The user's own observations (Beobachtungen) from Schiri-Beobachtung and Schiri-Portal.

    The frontend computes the averages: it needs the individual grades anyway
    for the expandable list, and per season it is a handful of rows.

    schiedsrichter_seit (referee since) is included because the tab shows the men's (Herren) seasons from
    this date on - including those without a single observation.
    """
    stammdaten = get_stammdaten(current_user['id']) or {}
    daten = get_beobachtungen(current_user['id'])
    daten["schiedsrichter_seit"] = stammdaten.get("schiedsrichter_seit") or None
    return daten


@app.get("/api/ligen")
async def get_ligen(current_user: dict = Depends(get_current_user)):
    """
    The reconciled league tables, highest Spielklasse (league level) first.

    The same data from which the expenses of cup and friendly matches
    are derived - anyone who wants to trace a rate sees the basis here.
    Not separated by user: a league table is the same for everyone.
    """
    staffeln = alle_staffeln()

    return {
        "bestand": bestand(),
        "staffeln": [{**staffel, "tabelle": tabelle(staffel["staffel_id"])} for staffel in staffeln],
    }


@app.get("/api/bugreport/status")
async def get_bug_report_status(current_user: dict = Depends(get_current_user)):
    """
    Whether mail can be sent from this server at all.

    The form asks beforehand: without an outbox it should not even
    invite submission, but say what is missing.
    """
    return {"verfuegbar": ist_konfiguriert(), "empfaenger": empfaenger()}


class BugReportRequest(BaseModel):
    """An error report from the tab of the same name."""
    titel: str
    beschreibung: str
    bereich: str = ""
    schritte: str = ""


@app.post("/api/bugreport")
async def post_bug_report(
    request: BugReportRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Sends an error report to the stored address.

    The sender is the logged-in user - their address is taken from the database
    and not from the form, otherwise this form could be used
    to write in someone else's name.
    """
    titel = request.titel.strip()
    beschreibung = request.beschreibung.strip()

    if not titel or not beschreibung:
        raise ValidationError("Titel und Beschreibung dürfen nicht leer sein")

    sende_bug_report(
        titel=titel,
        beschreibung=beschreibung,
        bereich=request.bereich.strip(),
        schritte=request.schritte.strip(),
        absender=current_user["email"],
    )

    return {"status": "gesendet"}


# ===== Frontend Routes =====
@app.get("/")
async def root():
    """Serve frontend root"""
    if not FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend not available")

    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    else:
        raise HTTPException(status_code=404, detail="Frontend not found")


def _wurzel_datei(full_path: str) -> Optional[FileResponse]:
    """
    A file directly in FRONTEND_DIR, otherwise None. Subdirectories and
    paths leading out of the directory do not count.

    The request only selects a name from the list of existing files;
    the served path always comes from the directory itself. That way
    no '..' or encoded slash can build the path.
    """
    wurzeldateien = {
        eintrag.name: eintrag
        for eintrag in FRONTEND_DIR.iterdir()
        if eintrag.is_file() and not eintrag.is_symlink() and eintrag.name != "index.html"
    }
    kandidat = wurzeldateien.get(full_path)
    if kandidat is None:
        return None

    media_type = "application/manifest+json" if kandidat.suffix == ".webmanifest" else None
    headers = {}
    if kandidat.name in ("sw.js", "manifest.webmanifest"):
        # Without this Cloudflare or the browser holds on to an old worker,
        # and an update no longer reaches the installed app.
        headers["Cache-Control"] = "no-cache"
    return FileResponse(str(kandidat), media_type=media_type, headers=headers)


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """
    Catch-all route for the frontend (React Router).
    Serves index.html for all non-API routes.
    """
    # Skip API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    # If the frontend is not available, 404
    if not FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend not available")

    # Files from frontend/public land directly in the dist root directory.
    # Manifest and service worker must live there: the worker only controls
    # addresses below its own path.
    datei = _wurzel_datei(full_path)
    if datei is not None:
        return datei

    # Serve index.html (for React Router)
    index_path = FRONTEND_DIR / "index.html"

    if index_path.exists():
        return FileResponse(str(index_path))
    else:
        raise HTTPException(status_code=404, detail="Frontend not found")