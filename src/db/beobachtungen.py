"""
Database access for a referee's own observations (Beobachtungen, grades).

Writing replaces per (quelle, saison) - as with the refereed
matches in season.py. Nothing on the rows is entered by the user themselves, and
new observations of the current season are released
gradually.
"""
from datetime import date, datetime, UTC
from typing import Dict, List, Optional, Set

from db.database import get_connection
from utils.logger import setup_logger
from utils.saison_utils import saison_start_jahr

logger = setup_logger("db_beobachtungen")

# How long after the end of a season it is still re-read. Observations
# of the last matchdays are often only released in July; whoever reads the season
# on 1 July and never again misses them.
_NACHLAUF_BIS_MONAT = 8  # read from 1 August on, the season counts as finished


def replace_beobachtungs_saison(
    user_id: int,
    quelle: str,
    saison: str,
    beobachtungen: List[Dict],
    scraped_at: Optional[str] = None,
) -> int:
    """
    Replaces the observations of a season from one source - in one
    transaction, so that never half a season is left behind.

    Returns:
            Number of observations written.
    """
    scraped_at = scraped_at or datetime.now(UTC).isoformat()
    conn = get_connection()

    try:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM beobachtungen WHERE user_id = ? AND quelle = ? AND saison = ?",
            (user_id, quelle, saison),
        )

        geschrieben = 0
        for b in beobachtungen:
            cursor = conn.execute("""
                INSERT INTO beobachtungen (
                    user_id, quelle, saison, datum, uhrzeit, spieltag, staffel,
                    heim, gast, ergebnis, rolle, note, note_text, beobachter,
                    freigegeben_am, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, quelle, saison, datum, uhrzeit, heim, gast, rolle)
                DO NOTHING
            """, (
                user_id, quelle, saison,
                b.get("datum") or "1900-01-01",
                b.get("uhrzeit") or "",
                b.get("spieltag") or "",
                b.get("staffel") or "",
                b.get("heim") or "",
                b.get("gast") or "",
                b.get("ergebnis") or "",
                b["rolle"],
                float(b["note"]),
                b.get("note_text") or "",
                b.get("beobachter") or "",
                b.get("freigegeben_am") or "",
                scraped_at,
            ))
            geschrieben += cursor.rowcount

        conn.execute("""
            INSERT INTO beobachtung_saisons (user_id, quelle, saison, anzahl, scraped_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id, quelle, saison) DO UPDATE SET
                anzahl = excluded.anzahl,
                scraped_at = excluded.scraped_at
        """, (user_id, quelle, saison, geschrieben, scraped_at))

        conn.commit()
        return geschrieben

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_beobachtungen(user_id: int, quelle: str, saison: str) -> int:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM beobachtungen WHERE user_id = ? AND quelle = ? AND saison = ?",
            (user_id, quelle, saison),
        ).fetchone()[0]
    finally:
        conn.close()


def get_fertige_beobachtungs_saisons(
    user_id: int, quelle: str, heute: Optional[date] = None
) -> Set[str]:
    """
    Seasons that no longer need to be read.

    A season is finished if it was read when it was already over for longer
    (from 1 August after its end). The current season and the
    one that has just ended are therefore never finished.
    """
    heute = heute or date.today()
    conn = get_connection()

    try:
        rows = conn.execute(
            "SELECT saison, scraped_at FROM beobachtung_saisons WHERE user_id = ? AND quelle = ?",
            (user_id, quelle),
        ).fetchall()
    finally:
        conn.close()

    fertig = set()
    for row in rows:
        start = saison_start_jahr(row["saison"], heute)
        if start is None:
            continue
        try:
            gelesen = datetime.fromisoformat(row["scraped_at"]).date()
        except ValueError:
            continue
        if gelesen >= date(start + 1, _NACHLAUF_BIS_MONAT, 1):
            fertig.add(row["saison"])
    return fertig


def get_beobachtungen(user_id: int) -> Dict:
    """
    Everything the tab needs: which seasons have been read per source and
    all own observations, newest first.
    """
    conn = get_connection()

    try:
        saisons = conn.execute("""
            SELECT quelle, saison, anzahl, scraped_at
            FROM beobachtung_saisons
            WHERE user_id = ?
        """, (user_id,)).fetchall()

        beobachtungen = conn.execute("""
            SELECT id, quelle, saison, datum, uhrzeit, spieltag, staffel, heim, gast,
                   ergebnis, rolle, note, note_text, beobachter, freigegeben_am
            FROM beobachtungen
            WHERE user_id = ?
            ORDER BY datum DESC, uhrzeit DESC
        """, (user_id,)).fetchall()

        return {
            "saisons": [dict(row) for row in saisons],
            "beobachtungen": [dict(row) for row in beobachtungen],
        }
    finally:
        conn.close()


def delete_beobachtungen(user_id: int) -> int:
    """Deletes all observations of a user (change of the DFBnet account)."""
    conn = get_connection()

    try:
        conn.execute("BEGIN")
        cursor = conn.execute("DELETE FROM beobachtungen WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM beobachtung_saisons WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
