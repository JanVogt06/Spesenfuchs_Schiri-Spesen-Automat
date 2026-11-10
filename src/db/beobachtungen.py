"""
Datenbankzugriff fuer die eigenen Beobachtungen (Noten) eines Schiedsrichters.

Geschrieben wird je (quelle, saison) ersetzend - wie bei den geleiteten
Spielen in season.py. An den Zeilen haengt nichts, was der Nutzer selbst
eingibt, und neue Beobachtungen der laufenden Saison werden nach und nach
freigegeben.
"""
from datetime import date, datetime, UTC
from typing import Dict, List, Optional, Set

from db.database import get_connection
from utils.logger import setup_logger
from utils.saison_utils import saison_start_jahr

logger = setup_logger("db_beobachtungen")

# Wie lange nach Saisonende eine Saison noch nachgelesen wird. Beobachtungen
# der letzten Spieltage werden oft erst im Juli freigegeben; wer die Saison
# am 1. Juli liest und dann nie wieder, verpasst sie.
_NACHLAUF_BIS_MONAT = 8  # gelesen ab dem 1. August gilt die Saison als fertig


def replace_beobachtungs_saison(
    user_id: int,
    quelle: str,
    saison: str,
    beobachtungen: List[Dict],
    scraped_at: Optional[str] = None,
) -> int:
    """
    Ersetzt die Beobachtungen einer Saison aus einer Quelle - in einer
    Transaktion, damit nie eine halbe Saison stehen bleibt.

    Returns:
        Anzahl geschriebener Beobachtungen.
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
    Saisons, die nicht mehr gelesen werden muessen.

    Fertig ist eine Saison, wenn sie gelesen wurde, als sie schon laenger
    vorbei war (ab dem 1. August nach ihrem Ende). Die laufende Saison und die
    gerade beendete sind damit nie fertig.
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
    Alles, was der Reiter braucht: welche Saisons je Quelle gelesen sind und
    alle eigenen Beobachtungen, neueste zuerst.
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
    """Loescht alle Beobachtungen eines Users (Wechsel des DFBnet-Kontos)."""
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
