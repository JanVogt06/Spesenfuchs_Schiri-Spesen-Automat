"""
Nightly fetch of the DFBnet assignments (Ansetzungen) for all users.

This scheduler used to create a session folder with JSON, DOCX and PDF per user
and night - with 21 users that was around 7700 files per year for a few
hundred distinct matches. Now it only writes to the database; documents are
generated on download.
"""
import asyncio
import multiprocessing
from datetime import datetime, timedelta
from typing import Any, Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.database import get_all_users, get_dfb_credentials, dfb_login_abgelehnt
from db.scrape_runs import start_run, update_run, fail_stale_runs
from core.encryption import decrypt_credential
from core.errors import DFBCredentialsInvalidError
from utils.logger import setup_logger

from main import scrape_matches

logger = setup_logger("auto_scheduler")

# How long a single per-user fetch may run at most. A full scrape including
# login takes a few minutes; after that the process is hung.
USER_TIMEOUT_SECONDS = 20 * 60


def run_scrape_for_user(user_id: int, email: str, dfb_username: str, dfb_password: str, run_id: int):
    """
    Scrapes the assignments of one user. Runs in a separate process because
    Playwright cannot run inside the asyncio loop.
    """
    process_logger = setup_logger("auto_scheduler_worker")

    try:
        process_logger.info(f"[User {user_id}] Starte Abruf")
        update_run(run_id, status="scraping", step="DFB Scraping...")

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
        process_logger.info(f"[User {user_id}] Abruf abgeschlossen: {anzahl} Spiele")

    except DFBCredentialsInvalidError as e:
        # Separate branch as in the API path: on this code the frontend sends
        # the user to the settings. Without it, after a nightly run they would
        # only see "an error occurred".
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
        # Only after the run: if this write fails, the run should still show
        # up as failed.
        dfb_login_abgelehnt(user_id)

    except Exception as e:
        process_logger.error(f"[User {user_id}] Fehler: {e}", exc_info=True)
        update_run(
            run_id,
            status="failed",
            step="Fehler",
            error_code="GENERATION_ERROR",
            error_message="Beim nächtlichen Abruf ist ein Fehler aufgetreten.",
            finished=True,
        )


class AutoScrapeScheduler:
    """Fetches the assignments of all users once per night"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._is_running = False
        logger.info("AutoScrapeScheduler initialisiert (sequenziell, ein User nach dem anderen)")

    async def process_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Starts the fetch for one user and waits until it is finished."""
        user_id = user['id']
        email = user['email']

        try:
            credentials = get_dfb_credentials(user_id)
            if not credentials:
                logger.warning(f"[User {user_id}] Keine DFB-Credentials - überspringe")
                return {"user_id": user_id, "email": email, "success": False, "reason": "no_credentials"}

            dfb_username = decrypt_credential(credentials['dfb_username_encrypted'])
            dfb_password = decrypt_credential(credentials['dfb_password_encrypted'])

            run_id = start_run(user_id)

            # Credentials passed directly as parameters (not via ENV!)
            process = multiprocessing.Process(
                target=run_scrape_for_user,
                args=(user_id, email, dfb_username, dfb_password, run_id),
                daemon=True
            )
            process.start()

            # Wait before the next user is processed - one browser is enough.
            # With a time limit: if a child process hangs, the whole nightly
            # run would otherwise be blocked and none of the following users
            # would ever get their turn.
            await asyncio.get_event_loop().run_in_executor(
                None, process.join, USER_TIMEOUT_SECONDS
            )

            if process.is_alive():
                logger.error(
                    f"[User {user_id}] Abruf laeuft nach {USER_TIMEOUT_SECONDS}s noch - "
                    "wird beendet"
                )
                process.terminate()
                await asyncio.get_event_loop().run_in_executor(None, process.join, 10)
                update_run(run_id, status="failed", step="Zeitüberschreitung",
                           error_code="GENERATION_ERROR",
                           error_message="Der Abruf hat zu lange gedauert und wurde beendet.",
                           finished=True)
                return {"user_id": user_id, "email": email, "success": False, "reason": "timeout"}

            logger.info(f"[User {user_id}] Prozess abgeschlossen")
            return {"user_id": user_id, "email": email, "success": True, "run_id": run_id}

        except Exception as e:
            logger.error(f"[User {user_id}] Fehler: {e}", exc_info=True)
            return {"user_id": user_id, "email": email, "success": False, "reason": str(e)}

    @staticmethod
    def _ligatabellen_vorhanden() -> bool:
        """Whether league tables have been fetched at least once."""
        try:
            from db.ligen import bestand

            return bool(bestand().get("mannschaften"))
        except Exception:
            return True   # when in doubt, trigger nothing

    @staticmethod
    def aktualisiere_ligatabellen():
        """
        Reconciles the league tables and fills in outstanding expense rates.

        Runs before the assignments are fetched, so that a cup match newly
        assigned today gets its rate right away instead of only the next
        night. An error here must not stop the fetch - the tables are an extra,
        the assignments are the purpose of the application.
        """
        try:
            from db.matches import ergaenze_offene_saetze
            from scraper.ligen_aktualisieren import aktualisiere_alle

            aktualisiere_alle()
            ergaenze_offene_saetze()
        except Exception as e:
            logger.error(f"Ligatabellen konnten nicht abgeglichen werden: {e}", exc_info=True)

    async def scrape_all_users(self):
        """Fetches the assignments of all users (nightly at 3 a.m.)."""
        if self._is_running:
            logger.warning("Abruf läuft bereits - überspringe doppelten Aufruf")
            return

        self._is_running = True
        # Clean up runs left over from crashed previous nights
        fail_stale_runs()
        self.aktualisiere_ligatabellen()
        logger.info("=" * 80)
        logger.info("AUTOMATISCHER ABRUF GESTARTET")
        logger.info(f"Zeitpunkt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        try:
            users = get_all_users()
            logger.info(f"Gefunden: {len(users)} User")

            if not users:
                logger.info("Keine User gefunden")
                return

            results = [await self.process_user(user) for user in users]

            successful = sum(1 for r in results if r.get("success"))
            logger.info("=" * 80)
            logger.info("AUTOMATISCHER ABRUF ABGESCHLOSSEN")
            logger.info(f"Gesamt: {len(users)} User, erfolgreich: {successful}, "
                        f"fehlgeschlagen: {len(users) - successful}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Kritischer Fehler: {e}", exc_info=True)
        finally:
            self._is_running = False

    def start(self):
        """Starts the scheduler"""
        self.scheduler.add_job(
            self.scrape_all_users,
            CronTrigger(hour=3, minute=0, timezone="Europe/Berlin"),
            id="auto_scrape",
            name="Automatischer DFBnet-Abruf (3 Uhr)",
            replace_existing=True
        )

        # On the very first start the league tables are empty, and without them
        # the *Ligen* tab stays empty until 3 a.m. and the cup expenses stay
        # undetermined. So catch up once shortly after startup - in the
        # scheduler and not in the startup sequence, so the application does
        # not wait on fussball.de before it becomes reachable.
        if not self._ligatabellen_vorhanden():
            self.scheduler.add_job(
                self.aktualisiere_ligatabellen,
                "date",
                run_date=datetime.now() + timedelta(seconds=30),
                id="ligen_erstbefuellung",
                name="Ligatabellen erstmalig holen",
                replace_existing=True,
            )
            logger.info("Ligatabellen fehlen - werden 30 Sekunden nach dem Start geholt")

        self.scheduler.start()
        logger.info("Scheduler gestartet - Abruf täglich um 3:00 Uhr")
        logger.info(f"Nächste Ausführung: {self.scheduler.get_job('auto_scrape').next_run_time}")

    def stop(self):
        """Stops the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler gestoppt")

    def get_status(self) -> Dict[str, Any]:
        """Status for the scheduler endpoint"""
        job = self.scheduler.get_job("auto_scrape")

        return {
            "running": self.scheduler.running,
            "is_processing": self._is_running,
            "next_run": str(job.next_run_time) if job else None,
        }
