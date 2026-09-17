"""
Datenbankzugriff fuer Scrape-Laeufe.

Ersetzt die metadata.json im Session-Ordner. Der Scraper laeuft in einem
eigenen Prozess (Playwright vertraegt sich nicht mit dem asyncio-Loop der API),
schrieb seinen Fortschritt bisher in diese Datei und die API las sie fuer den
2-Sekunden-Poll des Frontends wieder aus. Diese Tabelle ist jetzt der Kanal.
"""
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional

from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_scrape_runs")

# Laeuft ein Lauf laenger als das ohne Lebenszeichen, gilt sein Prozess als tot.
# Ein voller Scrape mit Login dauert wenige Minuten; alles darueber ist ein
# abgestuerztes Kind, das sonst fuer immer auf "scraping" stehen bliebe.
STALE_AFTER_MINUTES = 30

# Laeufe, die noch arbeiten
ACTIVE_STATUS = ("pending", "scraping", "generating")


def start_run(user_id: int) -> int:
    """Legt einen neuen Lauf an und gibt seine ID zurueck."""
    now = datetime.now(UTC).isoformat()
    conn = get_connection()

    try:
        cursor = conn.execute("""
            INSERT INTO scrape_runs (user_id, status, step, started_at, updated_at)
            VALUES (?, 'pending', 'Initialisierung...', ?, ?)
        """, (user_id, now, now))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_run(
    run_id: int,
    status: Optional[str] = None,
    step: Optional[str] = None,
    current: Optional[int] = None,
    total: Optional[int] = None,
    matches_found: Optional[int] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    finished: bool = False,
) -> None:
    """
    Schreibt den Fortschritt fort. Nur uebergebene Felder werden angefasst.

    Args:
        finished: Setzt zusaetzlich finished_at - fuer den letzten Aufruf
                  eines Laufs, egal ob erfolgreich oder nicht.
    """
    now = datetime.now(UTC).isoformat()

    fields = {
        "status": status,
        "step": step,
        "current_item": current,
        "total_items": total,
        "matches_found": matches_found,
        "error_code": error_code,
        "error_message": error_message,
    }
    updates = {name: value for name, value in fields.items() if value is not None}
    updates["updated_at"] = now

    if finished:
        updates["finished_at"] = now

    assignments = ", ".join(f"{name} = :{name}" for name in updates)
    conn = get_connection()

    try:
        conn.execute(
            f"UPDATE scrape_runs SET {assignments} WHERE id = :run_id",
            {**updates, "run_id": run_id},
        )
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: int) -> Optional[Dict]:
    """Einzelner Lauf, oder None."""
    conn = get_connection()

    try:
        row = conn.execute("SELECT * FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_latest_run(user_id: int) -> Optional[Dict]:
    """Der juengste Lauf eines Users - das, was das Frontend pollt."""
    conn = get_connection()

    try:
        row = conn.execute("""
            SELECT * FROM scrape_runs WHERE user_id = ?
            ORDER BY started_at DESC, id DESC LIMIT 1
        """, (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_runs(user_id: int, limit: int = 20) -> List[Dict]:
    """Die letzten Laeufe eines Users, neueste zuerst."""
    conn = get_connection()

    try:
        rows = conn.execute("""
            SELECT * FROM scrape_runs WHERE user_id = ?
            ORDER BY started_at DESC, id DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def has_active_run(user_id: int) -> bool:
    """Ob fuer den User gerade ein Lauf arbeitet (verhindert Doppelstarts)."""
    placeholders = ",".join("?" * len(ACTIVE_STATUS))
    conn = get_connection()

    try:
        row = conn.execute(f"""
            SELECT 1 FROM scrape_runs
            WHERE user_id = ? AND status IN ({placeholders})
            LIMIT 1
        """, (user_id, *ACTIVE_STATUS)).fetchone()
        return row is not None
    finally:
        conn.close()


def fail_stale_runs() -> int:
    """
    Schliesst Laeufe ab, deren Prozess offensichtlich gestorben ist.

    Der Scrape laeuft in einem daemonischen Kindprozess, den niemand
    ueberwacht. Stirbt er - OOM, Container-Neustart, Absturz in Playwright -
    blieb der Lauf bisher fuer immer auf "scraping" stehen und das Frontend
    pollte endlos. Wird beim Start und vor jedem neuen Lauf aufgerufen.

    Returns:
        Anzahl abgeraeumter Laeufe.
    """
    cutoff = (datetime.now(UTC) - timedelta(minutes=STALE_AFTER_MINUTES)).isoformat()
    now = datetime.now(UTC).isoformat()
    placeholders = ",".join("?" * len(ACTIVE_STATUS))
    conn = get_connection()

    try:
        cursor = conn.execute(f"""
            UPDATE scrape_runs
            SET status = 'failed',
                error_code = 'RUN_ABANDONED',
                error_message = 'Der Vorgang wurde unterbrochen. Bitte erneut starten.',
                step = 'Abgebrochen',
                updated_at = ?,
                finished_at = ?
            WHERE status IN ({placeholders}) AND updated_at < ?
        """, (now, now, *ACTIVE_STATUS, cutoff))
        conn.commit()

        if cursor.rowcount:
            logger.warning(f"{cursor.rowcount} verwaiste Scrape-Laeufe abgeraeumt")

        return cursor.rowcount
    finally:
        conn.close()
