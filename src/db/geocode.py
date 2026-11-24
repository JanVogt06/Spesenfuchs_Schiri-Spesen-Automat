"""
Cache for resolved addresses.

The map needs coordinates, DFBnet delivers plain text. Each address is
therefore looked up at the geocoder exactly once and kept here afterwards.
Over a season that is a handful of requests: the user's own
address is a single one, colleagues and venues repeat.

A failure is stored as well (lat/lon NULL), otherwise every
call of the map would run into the same unsuccessful request again. How long such a
failure stays valid is decided by the caller - the table only remembers when
it was asked.
"""
from datetime import datetime, UTC
from typing import Dict, Optional

from db.database import get_connection


def get_cached(anfrage: str, provider: str) -> Optional[Dict]:
    """
    Reads an entry for the request.

    None means "never asked". A hit with lat=None, by contrast, means
    "asked, but nothing found" - the two cases must
    stay distinguishable, otherwise a failure is repeated endlessly.
    """
    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT lat, lon, resolved_at FROM geocode_cache WHERE anfrage = ? AND provider = ?",
            (anfrage, provider),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return {"lat": row["lat"], "lon": row["lon"], "resolved_at": row["resolved_at"]}


def store(anfrage: str, provider: str, lat: Optional[float], lon: Optional[float]) -> None:
    """Records the result of a request - including the failure."""
    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT INTO geocode_cache (anfrage, provider, lat, lon, resolved_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (anfrage, provider) DO UPDATE SET
                lat = excluded.lat,
                lon = excluded.lon,
                resolved_at = excluded.resolved_at
            """,
            (anfrage, provider, lat, lon, datetime.now(UTC).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_ortsname(lat: float, lon: float, provider: str) -> Optional[Dict]:
    """The cached place name for a (rounded) coordinate: {"name", "resolved_at"}, or None if never asked."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT name, resolved_at FROM ortsnamen_cache WHERE lat = ? AND lon = ? AND provider = ?",
            (lat, lon, provider),
        ).fetchone()
    finally:
        conn.close()
    return {"name": row["name"], "resolved_at": row["resolved_at"]} if row else None


def store_ortsname(lat: float, lon: float, provider: str, name: Optional[str]) -> None:
    """Keeps the result of a reverse lookup - including "nothing found" (name None)."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO ortsnamen_cache (lat, lon, provider, name, resolved_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (lat, lon, provider) DO UPDATE SET
                name = excluded.name,
                resolved_at = excluded.resolved_at
            """,
            (lat, lon, provider, name, datetime.now(UTC).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
