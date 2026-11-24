"""
Lock after repeatedly wrong passwords.

After MAX_FEHLVERSUCHE wrong logins in a row the account is
locked for SPERRDAUER_MINUTEN; a correct login resets the counter.
If the last failed attempt lies further back than the lock duration,
counting starts over - anyone who mistypes once a month is never
locked.

The state lives in the database and not in memory, so that a
restart of the container does not lift the lock.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional

from db.database import get_connection

MAX_FEHLVERSUCHE = 5
SPERRDAUER_MINUTEN = 15


def _schluessel(email: str) -> str:
    """Case and whitespace must not circumvent the lock."""
    return email.strip().lower()


def gesperrt_bis(email: str, jetzt: Optional[datetime] = None) -> Optional[datetime]:
    """Point in time until which the address is locked - or None."""
    jetzt = jetzt or datetime.now(UTC)
    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT gesperrt_bis FROM login_sperren WHERE email = ?", (_schluessel(email),)
        ).fetchone()
    finally:
        conn.close()

    if not row or not row["gesperrt_bis"]:
        return None

    bis = datetime.fromisoformat(row["gesperrt_bis"])
    return bis if bis > jetzt else None


def fehlversuch_merken(email: str, jetzt: Optional[datetime] = None) -> int:
    """
    Counts a failed attempt.

    Returns:
            How many attempts remain until the lock. 0 means: this
            failed attempt triggered the lock.
    """
    jetzt = jetzt or datetime.now(UTC)
    schluessel = _schluessel(email)
    conn = get_connection()

    try:
        # IMMEDIATE: two simultaneous failed attempts must not both read the
        # old counter value and so swallow an attempt.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT fehlversuche, letzter_fehlversuch FROM login_sperren WHERE email = ?",
            (schluessel,),
        ).fetchone()

        bisher = 0
        if row:
            letzter = datetime.fromisoformat(row["letzter_fehlversuch"])
            if jetzt - letzter < timedelta(minutes=SPERRDAUER_MINUTEN):
                bisher = row["fehlversuche"]

        anzahl = bisher + 1
        sperre = None
        if anzahl >= MAX_FEHLVERSUCHE:
            sperre = (jetzt + timedelta(minutes=SPERRDAUER_MINUTEN)).isoformat()
            anzahl = 0  # after the lock expires there are full attempts again

        conn.execute("""
            INSERT INTO login_sperren (email, fehlversuche, letzter_fehlversuch, gesperrt_bis)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (email) DO UPDATE SET
                fehlversuche = excluded.fehlversuche,
                letzter_fehlversuch = excluded.letzter_fehlversuch,
                gesperrt_bis = excluded.gesperrt_bis
        """, (schluessel, anzahl, jetzt.isoformat(), sperre))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return 0 if sperre else MAX_FEHLVERSUCHE - anzahl


def fehlversuche_loeschen(email: str) -> None:
    """After a successful login."""
    conn = get_connection()

    try:
        conn.execute("DELETE FROM login_sperren WHERE email = ?", (_schluessel(email),))
        conn.commit()
    finally:
        conn.close()
