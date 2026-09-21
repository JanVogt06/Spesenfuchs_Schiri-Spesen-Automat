"""
Zwischenspeicher fuer aufgeloeste Adressen.

Die Karte braucht Koordinaten, DFBnet liefert Klartext. Jede Adresse wird
deshalb genau einmal beim Geocoder nachgeschlagen und danach hier behalten.
Ueber eine Saison hinweg sind das eine Handvoll Anfragen: die eigene
Anschrift ist eine einzige, Kollegen und Spielstaetten wiederholen sich.

Ein Fehlschlag wird ebenfalls gespeichert (lat/lon NULL), sonst liefe jeder
Aufruf der Karte erneut in dieselbe erfolglose Anfrage. Wie lange so ein
Fehlschlag gilt, entscheidet der Aufrufer - die Tabelle merkt sich nur, wann
gefragt wurde.
"""
from datetime import datetime, UTC
from typing import Dict, Optional

from db.database import get_connection


def get_cached(anfrage: str, provider: str) -> Optional[Dict]:
    """
    Liest einen Eintrag zur Anfrage.

    None heisst "noch nie gefragt". Ein Treffer mit lat=None heisst dagegen
    "gefragt, aber nichts gefunden" - die beiden Faelle muessen
    unterscheidbar bleiben, sonst wird ein Fehlschlag endlos wiederholt.
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
    """Haelt das Ergebnis einer Anfrage fest - auch den Fehlschlag."""
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
