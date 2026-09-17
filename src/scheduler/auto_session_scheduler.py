"""
Automatischer Session Scheduler - VEREINFACHT
Nutzt die bereits existierenden Funktionen aus main.py und main_api.py
"""
import asyncio
import multiprocessing
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.database import (
    get_all_users,
    get_dfb_credentials,
    create_session as db_create_session,
    update_session_status as db_update_session_status
)
from core.encryption import decrypt_credential
from utils.session_manager import SessionManager
from utils.logger import setup_logger

# Import der bestehenden Funktion aus main.py
from main import scrape_matches_with_session, generate_documents_in_session

logger = setup_logger("auto_scheduler")


def run_generation_for_user(
    user_id: int,
    email: str,
    dfb_username: str,
    dfb_password: str,
    session_path: Path,
    session_id: str
):
    """
    Führt die komplette Generierung für einen User aus.
    Läuft in einem separaten Prozess (wie der manuelle /api/generate Endpoint).

    NUTZT DIE BEREITS EXISTIERENDEN UND GETESTETEN FUNKTIONEN!

    Args:
        user_id: User-ID für Logging
        email: User-Email für Logging
        dfb_username: DFB.net Benutzername (entschlüsselt)
        dfb_password: DFB.net Passwort (entschlüsselt)
        session_path: Pfad zum Session-Ordner
        session_id: Session-ID für DB-Updates
    """
    # Logger im neuen Prozess initialisieren
    process_logger = setup_logger("auto_scheduler_worker")

    try:
        process_logger.info(f"[User {user_id}] Starte Generation für {email}")

        # Session Manager im Prozess initialisieren
        sm = SessionManager()

        # Status: Scraping
        sm.update_session_metadata(
            session_path,
            status="scraping",
            progress={"current": 0, "total": 0, "step": "DFB Scraping..."}
        )
        db_update_session_status(session_id, "scraping")

        # === NUTZE DIE BESTEHENDE FUNKTION AUS MAIN.PY MIT CREDENTIALS ===
        matches_data, _ = scrape_matches_with_session(
            session_path,
            username=dfb_username,
            password=dfb_password,
            user_id=user_id
        )

        if not matches_data:
            process_logger.warning(f"[User {user_id}] Keine Spiele gefunden")
            sm.update_session_metadata(
                session_path,
                status="completed",
                progress={"current": 0, "total": 0, "step": "Keine Spiele gefunden"}
            )
            db_update_session_status(session_id, "completed")
            return

        process_logger.info(f"[User {user_id}] {len(matches_data)} Spiele gescrapt")

        # Status: Generierung
        sm.update_session_metadata(
            session_path,
            status="generating",
            progress={"current": 0, "total": len(matches_data), "step": "Erstelle Dokumente..."}
        )
        db_update_session_status(session_id, "generating")

        # === NUTZE DIE BESTEHENDE FUNKTION AUS MAIN.PY ===
        generate_documents_in_session(matches_data, session_path, user_id)

        # Status: Abgeschlossen
        sm.update_session_metadata(session_path, status="completed")
        db_update_session_status(session_id, "completed")

        process_logger.info(f"[User {user_id}] Session erfolgreich abgeschlossen")

    except Exception as e:
        process_logger.error(f"[User {user_id}] Fehler: {e}", exc_info=True)
        sm = SessionManager()
        sm.update_session_metadata(session_path, status="failed")
        db_update_session_status(session_id, "failed")


class AutoSessionScheduler:
    """Automatischer Scheduler für nächtliche Session-Erstellung"""

    def __init__(self):
        """Initialisiert den Scheduler"""
        self.scheduler = AsyncIOScheduler()
        self.session_manager = SessionManager()
        self._is_running = False
        logger.info("AutoSessionScheduler initialisiert (sequenziell, ein User nach dem anderen)")

    async def process_user_session(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """
        Startet Session-Erstellung für einen User in einem separaten Prozess.
        """
        user_id = user['id']
        email = user['email']

        try:
            logger.info(f"[User {user_id}] Starte Session für {email}")

            # 1. DFB Credentials holen
            credentials = get_dfb_credentials(user_id)
            if not credentials:
                logger.warning(f"[User {user_id}] Keine DFB-Credentials - überspringe")
                return {
                    "user_id": user_id,
                    "email": email,
                    "success": False,
                    "reason": "no_credentials"
                }

            # Credentials entschlüsseln
            dfb_username = decrypt_credential(credentials['dfb_username_encrypted'])
            dfb_password = decrypt_credential(credentials['dfb_password_encrypted'])

            # 2. Session erstellen
            session_path = self.session_manager.create_session()
            session_id = session_path.name

            # In DB speichern
            db_create_session(session_id, user_id)

            logger.info(f"[User {user_id}] Session erstellt: {session_id}")

            # 3. Generierung in separatem Prozess starten
            # Credentials werden direkt als Parameter übergeben (nicht über ENV!)
            process = multiprocessing.Process(
                target=run_generation_for_user,
                args=(user_id, email, dfb_username, dfb_password, session_path, session_id),
                daemon=True
            )
            process.start()

            # Warte bis Prozess fertig ist, bevor der naechste User drankommt
            await asyncio.get_event_loop().run_in_executor(None, process.join)

            logger.info(f"[User {user_id}] Prozess abgeschlossen")

            return {
                "user_id": user_id,
                "email": email,
                "success": True,
                "session_id": session_id
            }

        except Exception as e:
            logger.error(f"[User {user_id}] Fehler: {e}", exc_info=True)
            return {
                "user_id": user_id,
                "email": email,
                "success": False,
                "reason": str(e)
            }

    async def create_sessions_for_all_users(self):
        """
        Erstellt Sessions für alle User (wird um 3 Uhr ausgeführt).
        """
        if self._is_running:
            logger.warning("Session-Erstellung läuft bereits - überspringe doppelten Aufruf")
            return

        self._is_running = True
        logger.info("=" * 80)
        logger.info("AUTOMATISCHE SESSION-ERSTELLUNG GESTARTET")
        logger.info(f"Zeitpunkt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        try:
            users = get_all_users()
            logger.info(f"Gefunden: {len(users)} User")

            if not users:
                logger.info("Keine User gefunden")
                return

            # Verarbeite alle User sequenziell, einen nach dem anderen
            results = []
            for user in users:
                result = await self.process_user_session(user)
                results.append(result)

            # Zusammenfassung
            successful = sum(1 for r in results if r.get("success"))
            failed = sum(1 for r in results if not r.get("success"))

            logger.info("=" * 80)
            logger.info("AUTOMATISCHE SESSION-ERSTELLUNG ABGESCHLOSSEN")
            logger.info(f"Gesamt: {len(users)} User")
            logger.info(f"Erfolgreich: {successful}")
            logger.info(f"Fehlgeschlagen: {failed}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Kritischer Fehler: {e}", exc_info=True)
        finally:
            self._is_running = False

    def start(self):
        """Startet den Scheduler"""
        self.scheduler.add_job(
            self.create_sessions_for_all_users,
            CronTrigger(hour=3, minute=0, timezone="Europe/Berlin"),
            id="auto_session_creation",
            name="Automatische Session-Erstellung (3 Uhr)",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Scheduler gestartet - Sessions werden täglich um 3:00 Uhr erstellt")
        logger.info(f"Nächste Ausführung: {self.scheduler.get_job('auto_session_creation').next_run_time}")

    def stop(self):
        """Stoppt den Scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler gestoppt")

    async def trigger_now(self):
        """Manuelles Triggern für Tests"""
        logger.info("Manueller Trigger - starte Session-Erstellung sofort")
        await self.create_sessions_for_all_users()


# Globale Scheduler-Instanz
_scheduler_instance = None


def get_scheduler() -> AutoSessionScheduler:
    """Gibt die globale Scheduler-Instanz zurück"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AutoSessionScheduler()
    return _scheduler_instance