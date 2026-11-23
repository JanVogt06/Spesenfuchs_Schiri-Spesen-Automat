"""
Sperre nach wiederholt falschem Passwort.

Nach MAX_FEHLVERSUCHE falschen Logins hintereinander ist das Konto
SPERRDAUER_MINUTEN lang gesperrt; ein richtiger Login setzt den Zaehler
zurueck. Liegt der letzte Fehlversuch laenger als die Sperrdauer zurueck,
beginnt die Zaehlung von vorn - wer sich einmal im Monat vertippt, wird nie
gesperrt.

Der Zustand liegt in der Datenbank und nicht im Speicher, damit ein
Neustart des Containers die Sperre nicht aufhebt.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional

from db.database import get_connection

MAX_FEHLVERSUCHE = 5
SPERRDAUER_MINUTEN = 15


def _schluessel(email: str) -> str:
    """Gross-/Kleinschreibung und Leerzeichen duerfen die Sperre nicht umgehen."""
    return email.strip().lower()


def gesperrt_bis(email: str, jetzt: Optional[datetime] = None) -> Optional[datetime]:
    """Zeitpunkt, bis zu dem die Adresse gesperrt ist - oder None."""
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
    Zaehlt einen Fehlversuch.

    Returns:
        Wie viele Versuche bis zur Sperre noch bleiben. 0 heisst: dieser
        Fehlversuch hat die Sperre ausgeloest.
    """
    jetzt = jetzt or datetime.now(UTC)
    schluessel = _schluessel(email)
    conn = get_connection()

    try:
        # IMMEDIATE: zwei gleichzeitige Fehlversuche duerfen nicht beide den
        # alten Zaehlerstand lesen und so einen Versuch verschlucken.
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
            anzahl = 0  # nach Ablauf der Sperre gibt es wieder volle Versuche

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
    """Nach einem erfolgreichen Login."""
    conn = get_connection()

    try:
        conn.execute("DELETE FROM login_sperren WHERE email = ?", (_schluessel(email),))
        conn.commit()
    finally:
        conn.close()
