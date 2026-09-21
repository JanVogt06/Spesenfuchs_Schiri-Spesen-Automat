"""
Die Thueringer Herren-Ligen und ihre Tabellen.

Gefuellt wird das jede Nacht aus fussball.de (siehe scraper.fussball_de).
Zwei Verwendungen: der Reiter *Ligen* zeigt die Tabellen, und die Spesen der
Pokal- und Freundschaftsspiele brauchen die Spielklasse der beteiligten
Mannschaften (§2 Abs. 3 und 4 der Spesenordnung).

Zur Zuordnung eines DFBnet-Namens auf eine Tabellenzeile siehe
finde_mannschaft - die Stelle entscheidet ueber Geld und ist entsprechend
misstrauisch gebaut.
"""
from datetime import datetime, UTC
from typing import Dict, List, Optional

from db.database import get_connection

# Rangfolge der Spielklassen fuer "die hoechstklassige am Spiel beteiligte
# Mannschaft" (§2 Abs. 3). Kleiner ist hoeher.
RANG = {
    "regionalliga": 2,
    "oberliga": 3,
    "verbandsliga": 4,
    "landesklasse": 5,
}


def rang(spielklasse: str) -> int:
    """Rang einer Spielklasse; unbekannte gelten als die niedrigste."""
    return RANG.get(spielklasse, 99)


def ersetze_staffel(staffel, tabelle: List) -> None:
    """
    Schreibt eine Staffel samt Tabelle neu.

    Vollstaendiger Austausch statt Zusammenfuehren: Auf- und Absteiger, ein
    zurueckgezogenes Team oder eine Staffelreform wuerden sonst als Karteileiche
    stehen bleiben - und eine Karteileiche in dieser Tabelle ist ein falscher
    Spesensatz.

    Eine leere Tabelle laesst die alten Zeilen stehen. Vor dem ersten Spieltag
    und bei einer Aenderung des Seitenaufbaus kommt nichts zurueck, und dann
    sind veraltete Daten besser als gar keine.
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
    """Alle bekannten Staffeln, hoechste Spielklasse zuerst."""
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
    """Die Tabelle einer Staffel, von Platz 1 an."""
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


def finde_mannschaft(name: str) -> Optional[Dict]:
    """
    Sucht eine DFBnet-Mannschaft in den gespeicherten Tabellen.

    Gibt None zurueck, sobald das Ergebnis nicht eindeutig ist - lieber keine
    Spesen als die falschen. Zwei Bedingungen muessen zusammen erfuellt sein:

    1. Vereinskern UND Mannschaftsnummer stimmen ueberein. Die Nummer ist
       nicht verhandelbar: "SG FC Saalfeld 3." und "FC Saalfeld" haben
       denselben Kern, spielen aber Kreisliga und Verbandsliga - ohne diese
       Bedingung wuerde aus 25 Euro 50.
    2. Es gibt genau eine solche Zeile. Tauchte derselbe Kern in zwei Staffeln
       auf, waere nicht zu entscheiden, welche gemeint ist.

    Returns:
        Zeile mit Spielklasse und Rang, oder None.
    """
    from scraper.fussball_de import mannschaftsnummer, vereinskern

    kern = vereinskern(name)
    if not kern:
        return None

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

    if len(treffer) != 1:
        return None

    return dict(treffer[0])


# Ab diesem Rang gilt eine Mannschaft als ueberregional (Regionalliga und
# hoeher, dazu die Oberligen). Fuer diese Spiele bleiben die Pokalspesen leer.
RANG_UEBERREGIONAL = RANG["oberliga"]


def kennt_ueberregionale_ligen() -> bool:
    """
    Sind die ueberregionalen Tabellen ueberhaupt vorhanden?

    Entscheidet darueber, ob aus "steht in keiner Tabelle" geschlossen werden
    darf, dass eine Mannschaft unterhalb der Landesklasse spielt. Fehlen die
    ueberregionalen Staffeln, koennte sie ebenso gut Oberliga spielen - dann
    ist nichts zu schliessen und es gibt keine Spesen.
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
    """Kurzer Ueberblick fuer Oberflaeche und Protokoll."""
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
