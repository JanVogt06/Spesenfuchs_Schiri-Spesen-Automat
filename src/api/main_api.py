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
from core import config
from core.config import load_environment

load_environment()

from scheduler import get_scheduler
from main import scrape_matches
from utils.logger import setup_logger
from utils.match_utils import generate_filename_from_match
from utils.pdf_converter import convert_docx_bytes_to_pdf
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
    log_download,
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


# ===== Scrape-Prozess =====

def run_scrape_process(dfb_username: str, dfb_password: str, user_id: int, run_id: int):
    """
    Fuehrt den Scrape in einem eigenen Prozess aus.

    Der eigene Prozess ist noetig, weil Playwright nicht im asyncio-Loop der
    API laufen kann. Der Fortschritt wandert ueber die Tabelle scrape_runs
    zurueck - frueher war das eine metadata.json im Session-Ordner.

    Dokumente werden hier nicht mehr erzeugt: sie entstehen beim Download.
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

    except Exception as e:
        process_logger.error(f"[User {user_id}] Fehler beim Scrape: {e}")
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
    Startet einen neuen Abruf der Ansetzungen.

    Es entsteht kein Ordner und keine Datei mehr - nur eine Zeile in
    scrape_runs, die das Frontend pollt, und danach Spiele in der Datenbank.
    """
    user_id = current_user['id']
    logger.info(f"User {current_user['email']} startet Abruf")

    from db.database import get_dfb_credentials
    from core.encryption import decrypt_credential

    dfb_creds = get_dfb_credentials(user_id)
    if not dfb_creds:
        raise CredentialsMissingError()

    dfb_username = decrypt_credential(dfb_creds['dfb_username_encrypted'])
    dfb_password = decrypt_credential(dfb_creds['dfb_password_encrypted'])

    # Laeufe, deren Prozess gestorben ist, vorher abraeumen - sonst haengt
    # der Poll des Frontends am alten Lauf fest
    fail_stale_runs()

    run_id = start_run(user_id)

    # Credentials werden direkt als Parameter uebergeben (nicht ueber ENV!)
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


async def _render_pdfs(documents: List[tuple]) -> List[Optional[bytes]]:
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

    pdf_bytes = (await _render_pdfs([(filename, docx_bytes)]))[0]

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

    pdfs: List[Optional[bytes]] = [None] * len(documents)
    if request.file_format in ("pdf", "both"):
        pdfs = await _render_pdfs(documents)

        # Auch ein TEILWEISER Ausfall ist ein Fehler. Frueher wurden fehlende
        # PDFs einfach uebersprungen und der User bekam ein HTTP 200 mit einem
        # unvollstaendigen Archiv, ohne es zu merken.
        fehlend = sum(1 for pdf in pdfs if pdf is None)
        if fehlend:
            raise APIError(503, "PDF_CONVERSION_FAILED",
                           f"Für {fehlend} von {len(documents)} Spielen konnte keine PDF "
                           "erzeugt werden. Bitte erneut versuchen oder die Word-Dokumente "
                           "herunterladen.")

    buffer = BytesIO()
    # Gleiche Dateinamen sind moeglich (zwei Turniere am selben Tag), deshalb
    # bekommt jeder Eintrag notfalls einen Zusatz - sonst laegen im Archiv zwei
    # Dateien gleichen Namens.
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
                archive.writestr(basis.replace(".docx", ".pdf"), pdf_bytes)

    zip_name = f"Spesen_{datetime.now().strftime('%Y-%m-%d')}.zip"

    for match, (filename, _) in zip(matches, documents):
        log_download(user_id, filename, request.file_format, match_id=match['id'])

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers=_content_disposition(zip_name),
    )


@app.post("/api/scheduler/trigger")
async def trigger_scheduler_now(current_user: dict = Depends(get_current_user)):
    """
    Startet den naechtlichen Abruf sofort (fuer Testzwecke).

    ACHTUNG: betrifft ALLE User.
    """
    logger.info(f"Manueller Scheduler-Trigger durch User {current_user['email']}")

    scheduler = get_scheduler()
    asyncio.create_task(scheduler.scrape_all_users())

    return {
        "success": True,
        "message": "Automatischer Abruf wurde gestartet",
        "note": "Die Verarbeitung läuft im Hintergrund und kann einige Minuten dauern"
    }


@app.get("/api/scheduler/status")
async def get_scheduler_status(current_user: dict = Depends(get_current_user)):
    """Status des naechtlichen Abrufs"""
    return get_scheduler().get_status()


@app.get("/api/health")
async def health_check():
    """Health Check Endpoint"""
    return {
        "status": "online",
        "service": "Spesenfuchs API",
        "version": config.APP_VERSION,
        "matches": count_distinct_matches()
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