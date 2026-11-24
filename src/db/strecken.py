"""
Cache for road distances.

Like db.geocode: a failure is recorded with meter NULL, otherwise
every call would run into the same unsuccessful request again. How long it
stays valid is decided by the caller (utils.routing).
"""
from datetime import datetime, UTC
from typing import Dict, Iterable, List, Optional, Tuple

from db.database import get_connection

Punkt = Tuple[float, float]
Paar = Tuple[Punkt, Punkt]


def get_strecken(paare: Iterable[Paar], provider: str) -> Dict[Paar, Dict]:
    """
    The stored entries for the pairs: {pair: {"meter", "resolved_at"}}.
    A missing pair has never been asked.
    """
    paare = list(dict.fromkeys(paare))
    if not paare:
        return {}

    conn = get_connection()
    try:
        gefunden = {}
        # Querying pair by pair keeps the SQL simple; rarely more than a few dozen
        for von, nach in paare:
            row = conn.execute(
                """SELECT meter, resolved_at FROM strecken_cache
                   WHERE von_lat = ? AND von_lon = ? AND nach_lat = ? AND nach_lon = ? AND provider = ?""",
                (*von, *nach, provider),
            ).fetchone()
            if row:
                gefunden[(von, nach)] = {"meter": row["meter"], "resolved_at": row["resolved_at"]}
        return gefunden
    finally:
        conn.close()


def store_strecken(eintraege: List[Tuple[Punkt, Punkt, Optional[float]]], provider: str) -> None:
    """Records results - also "no route found" (meter None)."""
    if not eintraege:
        return

    jetzt = datetime.now(UTC).isoformat()
    conn = get_connection()
    try:
        conn.executemany(
            """
            INSERT INTO strecken_cache (von_lat, von_lon, nach_lat, nach_lon, provider, meter, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (von_lat, von_lon, nach_lat, nach_lon, provider) DO UPDATE SET
                meter = excluded.meter,
                resolved_at = excluded.resolved_at
            """,
            [(*von, *nach, provider, meter, jetzt) for von, nach, meter in eintraege],
        )
        conn.commit()
    finally:
        conn.close()
