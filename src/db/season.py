"""
Datenbankzugriff fuer geleitete Spiele und die Saisonbilanz.

Quelle ist der DFBnet-Reiter "Spiele & Statistiken" - nicht zu verwechseln mit
`db/matches.py`: dort stehen die Ansetzungen, an denen die vom Nutzer
eingetragenen Fahrtkosten haengen, hier die bereits geleiteten Spiele mit
Ergebnis und Kartenstatistik.

Geschrieben wird saisonweise und ersetzend: `replace_saison` raeumt eine
Saison vollstaendig ab und schreibt sie neu. Das ist hier erlaubt und noetig,
anders als bei den Ansetzungen:

- An diesen Zeilen haengt nichts, was der Nutzer selbst eingegeben hat.
- DFBnet korrigiert Ergebnisse und Kartenzahlen nachtraeglich.
- Die laufende Saison waechst mit jedem Spieltag, und Lehrabende sowie
  Leistungspruefungen aendern sich laufend.

Ein Merge wie in matches.py waere hier also falsch: er wuerde eine von DFBnet
zurueckgenommene Korrektur fuer immer festhalten.
"""
import sqlite3
from datetime import datetime, UTC
from typing import Dict, List, Optional

from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_season")


def build_saison_match_key(datum: str, heim: str, gast: str, uhrzeit: str) -> str:
    """
    Kanonische Identitaet eines geleiteten Spiels innerhalb einer Saison.

    Die Anstosszeit gehoert hier - anders als beim Schluessel der Ansetzungen -
    dazu: diese Tabelle listet abgeschlossene Spiele, eine Verlegung ist darin
    kein zweiter Eintrag derselben Partie mehr, sondern taucht nur mit ihrem
    tatsaechlichen Termin auf. Zwei Begegnungen derselben Vereine am selben Tag
    (Turniere, Nachholspiele) blieben ohne die Zeit dagegen nicht trennbar.
    """
    return f"{datum}|{uhrzeit}|{(heim or '').strip()}|{(gast or '').strip()}"


def _als_zahl(wert) -> Optional[int]:
    """DFBnet schreibt '-' fuer 'nichts erfasst'; daraus wird NULL."""
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
    Ersetzt eine komplette Saison eines Users.

    Laeuft in einer Transaktion: entweder steht die Saison danach vollstaendig
    neu in der Datenbank, oder unveraendert wie vorher. Ein Abbruch mitten im
    Schreiben wuerde sonst eine halbe Saison hinterlassen, die von einer
    vollstaendigen nicht zu unterscheiden waere.

    Args:
        spiele: Dicts vom Scraper (datum, uhrzeit, liga, heim, gast, ergebnis,
                karten, gespann, eigene_rolle)
        einsaetze: Zeilen der Einsatz-Tabelle (rolle, geleitet,
                   zurueckgegeben, nicht_angetreten)
        lehrgaenge: lehrabend, lehrabend_online, leistungspruefung
        erwartet: von DFBnet gemeldete Trefferzahl (Default: Anzahl der
                  uebergebenen Spiele)
        vollstaendig: Ob die Saison komplett gelesen wurde. Nur dann wird sie
                      bei kuenftigen Laeufen uebersprungen.

    Returns:
        Anzahl geschriebener Spiele.
    """
    scraped_at = scraped_at or datetime.now(UTC).isoformat()
    conn = get_connection()

    try:
        conn.execute("BEGIN")

        # Kinder zuerst: ON DELETE CASCADE greift nur, wenn foreign_keys an
        # ist - das ist es zwar (database.get_connection), aber explizit
        # loeschen kostet nichts und macht die Absicht sichtbar.
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
                # Zwei Zeilen mit demselben Schluessel in einer Lieferung -
                # sollte nicht vorkommen, darf den Lauf aber nicht kippen.
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
    Saisons, die vollstaendig gespeichert sind und nicht neu gelesen werden
    muessen.

    Vollstaendig heisst: der Lauf hat sie als vollstaendig gemeldet, es liegen
    genau so viele Spiele vor wie DFBnet damals Treffer gemeldet hat, UND eine
    Einsatzbilanz ist da. Faellt nur eines davon aus, wird die Saison als Ganzes
    neu gelesen - eine halb ergaenzte Saison waere schlimmer als eine neu
    geholte.

    Die laufende Saison filtert der Aufrufer heraus; sie steht hier mit drin,
    weil diese Funktion nichts darueber weiss, welche das gerade ist.
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


def get_saisons(user_id: int) -> List[Dict]:
    """
    Alle gespeicherten Saisons eines Users, neueste zuerst.

    Die Liste wird aus BEIDEN Quellen gebildet. Eine Saison ohne ein einziges
    geleitetes Spiel ist kein Sonderfall, sondern der Normalzustand am
    Saisonanfang: die Lehrabende stehen dann schon in season_education,
    waehrend season_matches noch leer ist. Wer die Liste nur aus den Spielen
    ableitet, blendet genau diese Saison komplett aus.

    Sortiert wird ueber das Anfangsjahr im Namen ("26/27" -> 26) und nicht
    ueber das juengste Spiel: das gibt es bei einer leeren Saison nicht.
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
    Eine Saison mit allen Spielen, der Einsatzbilanz und den Lehrgaengen.

    Gibt None zurueck, wenn zu dieser Saison GAR NICHTS gespeichert ist - eine
    Saison ganz ohne Spiele, aber mit Lehrabenden, kommt dagegen mit leerer
    Spielliste zurueck.
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

        # Erst hier auf "gibt es nicht" entscheiden: eine Saison ohne Spiele,
        # aber mit Lehrabenden, ist am Saisonanfang der Normalfall.
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


def delete_saisons(user_id: int) -> int:
    """
    Loescht alle Saisondaten eines Users.

    Wird beim Wechsel des DFBnet-Kontos aufgerufen - die gespeicherten Spiele
    gehoeren dann einer anderen Person.

    Returns:
        Anzahl geloeschter Spiele.
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
