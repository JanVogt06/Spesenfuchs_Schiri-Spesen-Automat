"""
Database access for scrape runs.

Replaces the metadata.json in the session folder. The scraper runs in its
own process (Playwright does not get along with the API's asyncio loop),
used to write its progress into that file and the API read it back for the
frontend's 2-second poll. This table is now the channel.
"""
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional

from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_scrape_runs")

# If a run lasts longer than this without a sign of life, its process counts as dead.
# A full scrape with login takes a few minutes; anything beyond is a
# crashed child that would otherwise stay on "scraping" forever.
STALE_AFTER_MINUTES = 30

# Runs that are still working
ACTIVE_STATUS = ("pending", "scraping", "generating")


def start_run(user_id: int) -> int:
    """Creates a new run and returns its ID."""
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
    Writes progress forward. Only passed fields are touched.

    Args:
            finished: Additionally sets finished_at - for the last call
                                of a run, whether successful or not.
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
    """A single run, or None."""
    conn = get_connection()

    try:
        row = conn.execute("SELECT * FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_latest_run(user_id: int) -> Optional[Dict]:
    """The most recent run of a user - what the frontend polls."""
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
    """The latest runs of a user, newest first."""
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
    """Whether a run is currently working for the user (prevents double starts)."""
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
    Closes runs whose process has obviously died.

    The scrape runs in a daemonic child process that nobody
    monitors. If it dies - OOM, container restart, crash in Playwright -
    the run used to stay on "scraping" forever and the frontend
    polled endlessly. Called at startup and before every new run.

    Returns:
            Number of runs cleaned up.
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
