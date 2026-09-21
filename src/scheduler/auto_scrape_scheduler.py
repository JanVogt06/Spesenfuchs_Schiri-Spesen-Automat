"""
Naechtlicher Abruf der DFBnet-Ansetzungen fuer alle User.

Frueher legte dieser Scheduler pro User und Nacht einen Session-Ordner mit
JSON, DOCX und PDF an - bei 21 Usern waren das rund 7700 Dateien pro Jahr fuer
einige hundert verschiedene Spiele. Jetzt schreibt er nur noch in die
Datenbank; Dokumente entstehen beim Download.
"""
import asyncio
import multiprocessing
from datetime import datetime, timedelta
from typing import Any, Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.database import get_all_users, get_dfb_credentials
from db.scrape_runs import start_run, update_run, fail_stale_runs
from core.encryption import decrypt_credential
from core.errors import DFBCredentialsInvalidError
from utils.logger import setup_logger

from main import scrape_matches

logger = setup_logger("auto_scheduler")

# Wie lange ein einzelner User-Abruf hoechstens laufen darf. Ein voller Scrape
# mit Login dauert wenige Minuten; danach haengt der Prozess.
USER_TIMEOUT_SECONDS = 20 * 60


def run_scrape_for_user(user_id: int, email: str, dfb_username: str, dfb_password: str, run_id: int):
    """
    Scrapt die Ansetzungen eines Users. Laeuft in einem eigenen Prozess, weil
    Playwright nicht im asyncio-Loop laufen kann.
    """
    process_logger = setup_logger("auto_scheduler_worker")

    try:
        process_logger.info(f"[User {user_id}] Starte Abruf für {email}")
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
        # Eigener Zweig wie im API-Pfad: das Frontend schickt den Nutzer bei
        # diesem Code in die Einstellungen. Ohne ihn saehe er nach einem
        # naechtlichen Lauf nur "ein Fehler ist aufgetreten".
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
    """Ruft die Ansetzungen aller User einmal pro Nacht ab"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._is_running = False
        logger.info("AutoScrapeScheduler initialisiert (sequenziell, ein User nach dem anderen)")

    async def process_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Startet den Abruf fuer einen User und wartet, bis er fertig ist."""
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

            # Credentials direkt als Parameter (nicht ueber ENV!)
            process = multiprocessing.Process(
                target=run_scrape_for_user,
                args=(user_id, email, dfb_username, dfb_password, run_id),
                daemon=True
            )
            process.start()

            # Warten, bevor der naechste User drankommt - ein Browser genuegt.
            # Mit Zeitlimit: haengt ein Kindprozess, waere sonst der ganze
            # naechtliche Lauf blockiert und alle folgenden User kaemen nie dran.
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
        """Ob schon einmal Ligatabellen geholt wurden."""
        try:
            from db.ligen import bestand

            return bool(bestand().get("mannschaften"))
        except Exception:
            return True   # im Zweifel nichts anstossen

    @staticmethod
    def aktualisiere_ligatabellen():
        """
        Gleicht die Ligatabellen ab und traegt offene Spesensaetze nach.

        Vor dem Abruf der Ansetzungen, damit ein heute neu angesetztes
        Pokalspiel gleich seinen Satz bekommt statt erst in der naechsten
        Nacht. Ein Fehler hier darf den Abruf nicht aufhalten - die Tabellen
        sind eine Zugabe, die Ansetzungen sind der Zweck der Anwendung.
        """
        try:
            from db.matches import ergaenze_offene_saetze
            from scraper.ligen_aktualisieren import aktualisiere_alle

            aktualisiere_alle()
            ergaenze_offene_saetze()
        except Exception as e:
            logger.error(f"Ligatabellen konnten nicht abgeglichen werden: {e}", exc_info=True)

    async def scrape_all_users(self):
        """Ruft die Ansetzungen aller User ab (naechtlich um 3 Uhr)."""
        if self._is_running:
            logger.warning("Abruf läuft bereits - überspringe doppelten Aufruf")
            return

        self._is_running = True
        # Laeufe abgestuerzter Vornaechte abraeumen
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
        """Startet den Scheduler"""
        self.scheduler.add_job(
            self.scrape_all_users,
            CronTrigger(hour=3, minute=0, timezone="Europe/Berlin"),
            id="auto_scrape",
            name="Automatischer DFBnet-Abruf (3 Uhr)",
            replace_existing=True
        )

        # Beim allerersten Start sind die Ligatabellen leer, und ohne sie
        # bleibt der Reiter *Ligen* bis 3 Uhr nachts leer und die Pokalspesen
        # unbestimmt. Also einmal kurz nach dem Start nachholen - im Scheduler
        # und nicht im Startvorgang, damit die Anwendung nicht auf fussball.de
        # wartet, bevor sie erreichbar ist.
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
        """Stoppt den Scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler gestoppt")

    def get_status(self) -> Dict[str, Any]:
        """Status fuer den Scheduler-Endpunkt"""
        job = self.scheduler.get_job("auto_scrape")

        return {
            "running": self.scheduler.running,
            "is_processing": self._is_running,
            "next_run": str(job.next_run_time) if job else None,
        }
