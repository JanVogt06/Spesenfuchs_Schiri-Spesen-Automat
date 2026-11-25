"""
Database access for refereed matches and the season balance.

The source is the DFBnet tab "Spiele & Statistiken" - not to be confused with
`db/matches.py`: there the assignments are kept, to which the travel costs
entered by the user are attached; here the already refereed matches with
result and card statistics.

Writing is done season by season and replacing: `replace_saison` clears a
season completely and writes it anew. That is allowed and necessary here,
unlike with the assignments:

- Nothing on these rows was entered by the user themselves.
- DFBnet corrects results and card counts retroactively.
- The current season grows with every matchday, and training evenings (Lehrabende) as well as
    performance tests (Leistungspruefungen) keep changing.

A merge as in matches.py would therefore be wrong here: it would hold on forever to a correction
withdrawn by DFBnet.
"""
import sqlite3
from datetime import datetime, UTC
from typing import Dict, List, Optional

from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_season")


def build_saison_match_key(datum: str, heim: str, gast: str, uhrzeit: str) -> str:
    """
    Canonical identity of a refereed match within a season.

    The kick-off time is part of it here - unlike with the key of the assignments -:
    this table lists completed matches, a rescheduling in it
    is no longer a second entry of the same fixture but appears only with its
    actual date. Two meetings of the same clubs on the same day
    (tournaments, postponed matches) would not be separable without the time, however.
    """
    return f"{datum}|{uhrzeit}|{(heim or '').strip()}|{(gast or '').strip()}"


def _als_zahl(wert) -> Optional[int]:
    """DFBnet writes '-' for 'nothing recorded'; this becomes NULL."""
    try:
        return int(str(wert).strip())
    except (TypeError, ValueError):
        return None


def replace_saison(
    user_id: int,
    saison: str,
    spiele: List[Dict],
    einsaetze: List[Dict],
    lehrgaenge: Dict,
    erwartet: Optional[int] = None,
    vollstaendig: bool = True,
    scraped_at: Optional[str] = None,
) -> int:
    """
    Replaces a complete season of a user.

    Runs in one transaction: either the season is completely
    new in the database afterwards, or unchanged as before. An abort in the middle of
    writing would otherwise leave half a season behind, which could not be told apart
    from a complete one.

    Args:
            spiele: Dicts from the scraper (datum, uhrzeit, liga, heim, gast, ergebnis,
                            karten, gespann, eigene_rolle)
            einsaetze: Rows of the assignment table (rolle, geleitet,
                                  zurueckgegeben, nicht_angetreten)
            lehrgaenge: lehrabend, lehrabend_online, leistungspruefung
            erwartet: Number of hits reported by DFBnet (default: number of
                                matches passed in)
            vollstaendig: Whether the season was read completely. Only then is it
                                        skipped in future runs.

    Returns:
            Number of matches written.
    """
    scraped_at = scraped_at or datetime.now(UTC).isoformat()
    conn = get_connection()

    try:
        conn.execute("BEGIN")

        # Children first: ON DELETE CASCADE only works if foreign_keys is on
        # - which it is (database.get_connection), but deleting
        # explicitly costs nothing and makes the intent visible.
        conn.execute("""
            DELETE FROM season_match_officials
            WHERE season_match_id IN (
                SELECT id FROM season_matches WHERE user_id = ? AND saison = ?
            )
        """, (user_id, saison))
        conn.execute(
            "DELETE FROM season_matches WHERE user_id = ? AND saison = ?",
            (user_id, saison),
        )
        conn.execute(
            "DELETE FROM season_appearances WHERE user_id = ? AND saison = ?",
            (user_id, saison),
        )

        geschrieben = 0

        for spiel in spiele:
            datum = spiel.get("datum") or "1900-01-01"
            uhrzeit = spiel.get("uhrzeit") or ""
            heim = spiel.get("heim") or ""
            gast = spiel.get("gast") or ""

            cursor = conn.execute("""
                INSERT INTO season_matches (
                    user_id, saison, match_key, datum, uhrzeit, liga, heim, gast,
                    ergebnis, heim_gelb, heim_gelbrot, heim_rot,
                    gast_gelb, gast_gelbrot, gast_rot, eigene_rolle, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, saison, match_key) DO NOTHING
            """, (
                user_id, saison,
                build_saison_match_key(datum, heim, gast, uhrzeit),
                datum, uhrzeit,
                spiel.get("liga") or "", heim, gast,
                spiel.get("ergebnis") or "",
                _als_zahl(spiel.get("heim_gelb")),
                _als_zahl(spiel.get("heim_gelbrot")),
                _als_zahl(spiel.get("heim_rot")),
                _als_zahl(spiel.get("gast_gelb")),
                _als_zahl(spiel.get("gast_gelbrot")),
                _als_zahl(spiel.get("gast_rot")),
                spiel.get("eigene_rolle") or "",
                scraped_at,
            ))

            if not cursor.lastrowid or cursor.rowcount == 0:
                # Two rows with the same key in one delivery -
                # should not happen, but must not tip over the run.
                logger.warning(f"[User {user_id}] {saison}: doppeltes Spiel uebersprungen")
                continue

            match_id = cursor.lastrowid
            geschrieben += 1

            seq_pro_rolle: Dict[str, int] = {}
            for person in spiel.get("gespann") or []:
                rolle = (person.get("rolle") or "").strip() or "SR"
                seq = seq_pro_rolle.get(rolle, 0)
                seq_pro_rolle[rolle] = seq + 1

                conn.execute("""
                    INSERT INTO season_match_officials
                        (season_match_id, rolle, seq, name, ist_selbst)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    match_id, rolle, seq,
                    (person.get("name") or "").strip(),
                    1 if person.get("selbst") else 0,
                ))

        for seq, zeile in enumerate(einsaetze):
            rolle = (zeile.get("rolle") or "").strip()
            if not rolle:
                continue

            conn.execute("""
                INSERT INTO season_appearances
                    (user_id, saison, rolle, seq, geleitet, zurueckgegeben, nicht_angetreten)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, saison, rolle) DO UPDATE SET
                    seq = excluded.seq,
                    geleitet = excluded.geleitet,
                    zurueckgegeben = excluded.zurueckgegeben,
                    nicht_angetreten = excluded.nicht_angetreten
            """, (
                user_id, saison, rolle, seq,
                (zeile.get("geleitet") or "").strip(),
                (zeile.get("zurueckgegeben") or "").strip(),
                (zeile.get("nicht_angetreten") or "").strip(),
            ))

        conn.execute("""
            INSERT INTO season_education
                (user_id, saison, lehrabend, lehrabend_online, leistungspruefung,
                 spiele_erwartet, vollstaendig, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, saison) DO UPDATE SET
                lehrabend = excluded.lehrabend,
                lehrabend_online = excluded.lehrabend_online,
                leistungspruefung = excluded.leistungspruefung,
                spiele_erwartet = excluded.spiele_erwartet,
                vollstaendig = excluded.vollstaendig,
                scraped_at = excluded.scraped_at
        """, (
            user_id, saison,
            (lehrgaenge.get("lehrabend") or "").strip(),
            (lehrgaenge.get("lehrabend_online") or "").strip(),
            (lehrgaenge.get("leistungspruefung") or "").strip(),
            len(spiele) if erwartet is None else erwartet,
            1 if vollstaendig else 0,
            scraped_at,
        ))

        conn.commit()
        return geschrieben

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_komplette_saisons(user_id: int) -> set:
    """
    Seasons that are completely stored and do not need to be
    read again.

    Complete means: the run reported them as complete, exactly as many matches are present
    as DFBnet reported hits back then, AND a
    duty balance is there. If only one of these is missing, the season is read again as a whole
    - a half-filled season would be worse than a freshly
    fetched one.

    The caller filters out the current season; it is included here
    because this function knows nothing about which one that currently is.
    """
    conn = get_connection()

    try:
        rows = conn.execute("""
            SELECT e.saison
            FROM season_education e
            WHERE e.user_id = :uid
              AND e.vollstaendig = 1
              AND e.spiele_erwartet = (
                    SELECT COUNT(*) FROM season_matches m
                     WHERE m.user_id = :uid AND m.saison = e.saison
              )
              AND EXISTS (
                    SELECT 1 FROM season_appearances a
                     WHERE a.user_id = :uid AND a.saison = e.saison
              )
        """, {"uid": user_id}).fetchall()
        return {row["saison"] for row in rows}
    finally:
        conn.close()


def count_saison_spiele(user_id: int, saison: str) -> int:
    """How many refereed matches are stored for a season of a user."""
    conn = get_connection()

    try:
        return conn.execute(
            "SELECT COUNT(*) FROM season_matches WHERE user_id = ? AND saison = ?",
            (user_id, saison),
        ).fetchone()[0]
    finally:
        conn.close()


def get_saisons(user_id: int) -> List[Dict]:
    """
    All stored seasons of a user, newest first.

    The list is formed from BOTH sources. A season without a single
    refereed match is not a special case but the normal state at the
    start of a season: the training evenings are then already in season_education,
    while season_matches is still empty. Anyone who derives the list only from the matches
    hides exactly this season completely.

    Sorting is by the start year in the name ("26/27" -> 26) and not
    by the most recent match: there is none for an empty season.
    """
    conn = get_connection()

    try:
        rows = conn.execute("""
            WITH saisons AS (
                SELECT saison FROM season_matches WHERE user_id = :uid
                UNION
                SELECT saison FROM season_education WHERE user_id = :uid
            )
            SELECT s.saison,
                   (SELECT COUNT(*) FROM season_matches m
                     WHERE m.user_id = :uid AND m.saison = s.saison) AS spiele,
                   (SELECT MAX(datum) FROM season_matches m
                     WHERE m.user_id = :uid AND m.saison = s.saison) AS letztes_spiel,
                   (SELECT e.scraped_at FROM season_education e
                     WHERE e.user_id = :uid AND e.saison = s.saison) AS scraped_at
            FROM saisons s
            ORDER BY CAST(substr(s.saison, 1, 2) AS INTEGER) DESC
        """, {"uid": user_id}).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_saison(user_id: int, saison: str) -> Optional[Dict]:
    """
    One season with all matches, the duty balance and the courses (Lehrgaenge).

    Returns None if NOTHING at all is stored for this season - a
    season without matches but with training evenings, by contrast, comes back with an empty
    match list.
    """
    conn = get_connection()

    try:
        spiel_rows = conn.execute("""
            SELECT * FROM season_matches
            WHERE user_id = ? AND saison = ?
            ORDER BY datum DESC, uhrzeit DESC
        """, (user_id, saison)).fetchall()

        spiele = [dict(row) for row in spiel_rows]
        nach_id = {spiel["id"]: spiel for spiel in spiele}
        for spiel in spiele:
            spiel["gespann"] = []

        if nach_id:
            platzhalter = ",".join("?" * len(nach_id))
            offizielle = conn.execute(f"""
                SELECT * FROM season_match_officials
                WHERE season_match_id IN ({platzhalter})
                ORDER BY season_match_id, rolle, seq
            """, tuple(nach_id)).fetchall()

            for reihe in offizielle:
                person = dict(reihe)
                nach_id[person["season_match_id"]]["gespann"].append({
                    "rolle": person["rolle"],
                    "name": person["name"],
                    "ist_selbst": bool(person["ist_selbst"]),
                })

        einsaetze = conn.execute("""
            SELECT rolle, geleitet, zurueckgegeben, nicht_angetreten
            FROM season_appearances
            WHERE user_id = ? AND saison = ?
            ORDER BY seq
        """, (user_id, saison)).fetchall()

        lehrgaenge = conn.execute("""
            SELECT lehrabend, lehrabend_online, leistungspruefung, scraped_at
            FROM season_education
            WHERE user_id = ? AND saison = ?
        """, (user_id, saison)).fetchone()

        # Only here decide on "does not exist": a season without matches,
        # but with training evenings, is the normal case at the start of a season.
        if not spiele and not einsaetze and not lehrgaenge:
            return None

        return {
            "saison": saison,
            "spiele": spiele,
            "einsaetze": [dict(row) for row in einsaetze],
            "lehrgaenge": dict(lehrgaenge) if lehrgaenge else None,
        }
    finally:
        conn.close()


def get_eigene_rollen(user_id: int) -> List[Dict]:
    """
    Season, date, teams, league and own role of all refereed matches - for
    matching other sources and for the statistics, which count exactly these.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT saison, datum, uhrzeit, heim, gast, liga, eigene_rolle FROM season_matches WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_saisons(user_id: int) -> int:
    """
    Deletes all season data of a user.

    Called when the DFBnet account is changed - the stored matches
    then belong to another person.

    Returns:
            Number of matches deleted.
    """
    conn = get_connection()

    try:
        conn.execute("BEGIN")
        conn.execute("""
            DELETE FROM season_match_officials
            WHERE season_match_id IN (SELECT id FROM season_matches WHERE user_id = ?)
        """, (user_id,))
        cursor = conn.execute("DELETE FROM season_matches WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM season_appearances WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM season_education WHERE user_id = ?", (user_id,))
        conn.commit()

        if cursor.rowcount:
            logger.info(f"[User {user_id}] {cursor.rowcount} geleitete Spiele geloescht")

        return cursor.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
