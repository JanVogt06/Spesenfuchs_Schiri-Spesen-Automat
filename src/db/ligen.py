"""
The Thuringian men's (Herren) leagues and their tables.

This is filled every night from fussball.de (see scraper.fussball_de).
Two uses: the *Ligen* tab shows the tables, and the expenses of
cup and friendly matches need the Spielklasse (league level) of the participating
teams (§2 para. 3 and 4 of the expense regulations, Spesenordnung).

For mapping a DFBnet name to a table row see
finde_mannschaft - this place decides about money and is built
accordingly distrustful.
"""
from datetime import datetime, UTC
from typing import Dict, List, Optional

from db.database import get_connection

# Ranking of the Spielklassen for "the highest-ranked team
# involved in the match" (§2 para. 3). Smaller is higher.
RANG = {
    "regionalliga": 2,
    "oberliga": 3,
    "verbandsliga": 4,
    "landesklasse": 5,
}


def rang(spielklasse: str) -> int:
    """Rank of a Spielklasse; unknown ones count as the lowest."""
    return RANG.get(spielklasse, 99)


def ersetze_staffel(staffel, tabelle: List) -> None:
    """
    Rewrites a Staffel (division) including its table.

    Complete replacement instead of merging: promoted and relegated teams, a
    withdrawn team or a division reform would otherwise remain as a stale
    record - and a stale record in this table is a wrong
    expense rate.

    An empty table leaves the old rows in place. Before the first matchday
    and when the page layout changes nothing comes back, and then
    outdated data is better than none at all.
    """
    from scraper.fussball_de import mannschaftsnummer, vereinskern

    if not tabelle:
        return

    jetzt = datetime.now(UTC).isoformat()
    conn = get_connection()

    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO liga_staffeln
                (staffel_id, pfad, spielklasse, verband, anzeigename, rang, aktualisiert_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (staffel_id) DO UPDATE SET
                pfad = excluded.pfad,
                anzeigename = excluded.anzeigename,
                rang = excluded.rang,
                aktualisiert_at = excluded.aktualisiert_at
            """,
            (staffel.staffel_id, staffel.pfad, staffel.spielklasse, staffel.verband,
             staffel.anzeigename, rang(staffel.spielklasse), jetzt),
        )
        conn.execute("DELETE FROM liga_tabellen WHERE staffel_id = ?", (staffel.staffel_id,))
        conn.executemany(
            """
            INSERT INTO liga_tabellen
                (staffel_id, team_id, platz, mannschaft, kern, nummer,
                 spiele, siege, unentschieden, niederlagen, tore, gegentore, punkte)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (staffel.staffel_id, p.team_id, p.platz, p.mannschaft,
                 vereinskern(p.mannschaft), mannschaftsnummer(p.mannschaft),
                 p.spiele, p.siege, p.unentschieden, p.niederlagen,
                 p.tore, p.gegentore, p.punkte)
                for p in tabelle
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def alle_staffeln() -> List[Dict]:
    """All known divisions (Staffeln), highest Spielklasse first."""
    conn = get_connection()

    try:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT s.*, COUNT(t.team_id) AS mannschaften
                FROM liga_staffeln s
                LEFT JOIN liga_tabellen t ON t.staffel_id = s.staffel_id
                GROUP BY s.staffel_id
                ORDER BY s.rang, s.anzeigename
                """
            )
        ]
    finally:
        conn.close()


def tabelle(staffel_id: str) -> List[Dict]:
    """The table of a division, from place 1."""
    conn = get_connection()

    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM liga_tabellen WHERE staffel_id = ? ORDER BY platz",
                (staffel_id,),
            )
        ]
    finally:
        conn.close()


def suche_mannschaft(name: str) -> List[Dict]:
    """
    All table rows that match a DFBnet team.

    Matching means: club core AND team number agree. The
    number is non-negotiable: "SG FC Saalfeld 3." and "FC Saalfeld"
    have the same core, but play Kreisliga and Verbandsliga - without this
    condition 25 euros would become 50.

    Whoever derives money from this must distinguish "no row" from "several rows":
    the first means "plays in no recorded league",
    the second "plays in one of them, but it cannot be determined which".
    """
    from scraper.fussball_de import mannschaftsnummer, vereinskern

    kern = vereinskern(name)
    if not kern:
        return []

    conn = get_connection()

    try:
        treffer = conn.execute(
            """
            SELECT t.*, s.spielklasse, s.verband, s.anzeigename, s.rang
            FROM liga_tabellen t
            JOIN liga_staffeln s ON s.staffel_id = t.staffel_id
            WHERE t.kern = ? AND t.nummer = ?
            """,
            (kern, mannschaftsnummer(name)),
        ).fetchall()
    finally:
        conn.close()

    return [dict(zeile) for zeile in treffer]


def finde_mannschaft(name: str) -> Optional[Dict]:
    """
    The one table row of a DFBnet team, or None.

    None as soon as the result is not unambiguous - better no expenses than
    the wrong ones. If the same core with the same number appeared in two divisions,
    it could not be decided which is meant. For the distinction from
    "not found" see suche_mannschaft.
    """
    treffer = suche_mannschaft(name)
    return treffer[0] if len(treffer) == 1 else None


# From this rank a team counts as supra-regional (Regionalliga and
# higher, plus the Oberligen). For these matches the cup expenses stay empty.
RANG_UEBERREGIONAL = RANG["oberliga"]


def kennt_ueberregionale_ligen() -> bool:
    """
    Are the supra-regional tables present at all?

    Decides whether it may be concluded from "appears in no table"
    that a team plays below the Landesklasse. If the
    supra-regional divisions are missing, it could just as well play Oberliga - then
    nothing can be concluded and there are no expenses.
    """
    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM liga_staffeln WHERE rang <= ?",
            (RANG_UEBERREGIONAL,),
        ).fetchone()
    finally:
        conn.close()

    return bool(row and row["n"])


def bestand() -> Dict[str, object]:
    """Short overview for the UI and the log."""
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT s.staffel_id) AS staffeln,
                   COUNT(t.team_id)             AS mannschaften,
                   MAX(s.aktualisiert_at)       AS aktualisiert_at
            FROM liga_staffeln s
            LEFT JOIN liga_tabellen t ON t.staffel_id = s.staffel_id
            """
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else {"staffeln": 0, "mannschaften": 0, "aktualisiert_at": None}
