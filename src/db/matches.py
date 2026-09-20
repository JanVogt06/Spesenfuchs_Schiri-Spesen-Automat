"""
Datenbankzugriff fuer Spiele, Unparteiische und deren Fahrtkosten.

Die Spiele lagen frueher nur als spesen_data.json in den Session-Ordnern. Hier
werden sie gelesen und geschrieben - in genau der Struktur, die der Scraper
liefert und der Generator erwartet ('spiel_info', 'schiedsrichter',
'spielstaette'), damit an beiden Enden nichts umgebaut werden muss.
"""
import sqlite3
from datetime import datetime, UTC
from typing import Dict, List, Optional

from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_matches")

# Reihenfolge der Rollen im Formular. Die Vorlage hat genau drei Spalten;
# weitere Unparteiische (Turniertage mit mehreren SR) werden gespeichert,
# aber nicht ins Dokument uebernommen.
FORM_ROLES = [("SR", 0, "sr"), ("SRA 1", 0, "sra1"), ("SRA 2", 0, "sra2")]

# Felder, die beim erneuten Scrapen nur uebernommen werden, wenn der Scraper
# tatsaechlich einen Wert geliefert hat. Er gibt bei Teilfehlern leere Strings
# zurueck - ein blindes Ueberschreiben wuerde gute Daten vernichten.
_MERGE_FIELDS = [
    "heim_team", "gast_team", "anpfiff", "mannschaftsart", "spielklasse",
    "staffel", "spieltag", "staette_name", "staette_adresse", "staette_platz_typ",
]


def build_match_key(spiel_info: Dict, spielstaette: Dict, datum: str) -> str:
    """
    Baut die kanonische Identitaet eines Spiels.

    DFBnet liefert derzeit keine Spielnummer, also bleibt nur Heim + Gast +
    Datum. Sobald die Spielnummer verfuegbar ist, wird sie hier zum Schluessel
    und alles andere bleibt unveraendert.

    Turnier-Ansetzungen haben keine Teams (dafuer mehrere Unparteiische in der
    Rolle SR). Fuer sie treten Spielstaette und Anpfiff an die Stelle der
    Teams, sonst wuerden zwei Turniere am selben Tag zu einer Zeile kollabieren.
    """
    heim = (spiel_info.get("heim_team") or "").strip()
    gast = (spiel_info.get("gast_team") or "").strip()

    if heim and gast:
        return f"{heim}|{gast}|{datum}"

    staette = (spielstaette.get("name") or "").strip()
    anpfiff = (spiel_info.get("anpfiff") or "").strip()

    return f"turnier|{staette}|{anpfiff or datum}"


def _expense_prefix(rolle: str, seq: int) -> Optional[str]:
    """Rolle -> Praefix der Formularfelder (sr/sra1/sra2), oder None."""
    for form_rolle, form_seq, prefix in FORM_ROLES:
        if rolle == form_rolle and seq == form_seq:
            return prefix
    return None


def upsert_match(
    user_id: int,
    match_data: Dict,
    datum: str,
    sr_spesen: Optional[float],
    sra_spesen: Optional[float],
    km_satz: float,
    scraped_at: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Legt ein Spiel an oder aktualisiert es und ersetzt die Unparteiischen.

    Zwei Dinge werden bewusst NICHT ueberschrieben, wenn das Spiel schon
    existiert:

    - die eingefrorenen Spesensaetze und der km-Satz. Sie gelten ab dem ersten
      Scrape, damit eine spaetere Aenderung der Spesenordnung keine bereits
      abgegebene Abrechnung rueckwirkend umschreibt.
    - leere Felder aus einem Teilfehler des Scrapers (siehe _MERGE_FIELDS).

    Die erfassten Fahrtkosten haengen an (match_id, rolle, seq) in einer
    eigenen Tabelle und ueberleben das Ersetzen der Unparteiischen.

    Returns:
        Die ID des Spiels.
    """
    own_conn = conn is None
    conn = conn or get_connection()
    scraped_at = scraped_at or datetime.now(UTC).isoformat()

    spiel_info = match_data.get("spiel_info", {}) or {}
    spielstaette = match_data.get("spielstaette", {}) or {}
    schiedsrichter = match_data.get("schiedsrichter", []) or []

    match_key = build_match_key(spiel_info, spielstaette, datum)

    values = {
        "user_id": user_id,
        "match_key": match_key,
        "heim_team": (spiel_info.get("heim_team") or "").strip(),
        "gast_team": (spiel_info.get("gast_team") or "").strip(),
        "datum": datum,
        "anpfiff": spiel_info.get("anpfiff") or "",
        "mannschaftsart": spiel_info.get("mannschaftsart") or "",
        "spielklasse": spiel_info.get("spielklasse") or "",
        "staffel": spiel_info.get("staffel") or "",
        "spieltag": spiel_info.get("spieltag") or "",
        "staette_name": spielstaette.get("name") or "",
        "staette_adresse": spielstaette.get("adresse") or "",
        "staette_platz_typ": spielstaette.get("platz_typ") or "",
        "sr_spesen": sr_spesen,
        "sra_spesen": sra_spesen,
        "km_satz": km_satz,
        "first_seen_at": scraped_at,
        "scraped_at": scraped_at,
    }

    # Nur nicht-leere Werte uebernehmen; '' bedeutet "Scraper hat nichts
    # geliefert", nicht "Feld ist jetzt leer".
    merge_sets = ",\n            ".join(
        f"{field} = COALESCE(NULLIF(excluded.{field}, ''), matches.{field})"
        for field in _MERGE_FIELDS
    )

    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    try:
        conn.execute(f"""
            INSERT INTO matches ({columns})
            VALUES ({placeholders})
            ON CONFLICT (user_id, match_key) DO UPDATE SET
                {merge_sets},
                datum = COALESCE(NULLIF(excluded.datum, '1900-01-01'), matches.datum),
                scraped_at = excluded.scraped_at,
                missing_since = NULL
        """, values)

        # Nicht lastrowid verwenden: nach ON CONFLICT DO UPDATE zeigt es nicht
        # zuverlaessig auf die aktualisierte Zeile.
        match_id = conn.execute(
            "SELECT id FROM matches WHERE user_id = ? AND match_key = ?",
            (user_id, match_key),
        ).fetchone()["id"]

        # Schnappschuss der Unparteiischen ersetzen - aber nur, wenn der
        # Scrape welche geliefert hat. Sonst bliebe das Dokument namenlos.
        if schiedsrichter:
            conn.execute("DELETE FROM match_officials WHERE match_id = ?", (match_id,))

            seq_per_rolle: Dict[str, int] = {}
            besetzt = []
            for person in schiedsrichter:
                rolle = (person.get("rolle") or "").strip() or "SR"
                seq = seq_per_rolle.get(rolle, 0)
                seq_per_rolle[rolle] = seq + 1
                besetzt.append((rolle, seq))

                conn.execute("""
                    INSERT INTO match_officials
                        (match_id, rolle, seq, name, telefon, email, strasse, plz_ort)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    match_id, rolle, seq,
                    person.get("name") or "",
                    person.get("telefon") or "",
                    person.get("email") or "",
                    person.get("strasse") or "",
                    person.get("plz_ort") or "",
                ))

            # Fahrtkosten von Rollen wegraeumen, die es nicht mehr gibt. Wird
            # eine Assistenz zurueckgezogen, blieben ihre Kilometer sonst als
            # Waise liegen: official_expenses haengt an matches, nicht an
            # match_officials, und im Formular gaebe es keine Zeile mehr, ueber
            # die man sie loeschen koennte - im Dokument staenden sie trotzdem.
            if besetzt:
                platzhalter = ",".join("(?,?)" for _ in besetzt)
                werte = [teil for paar in besetzt for teil in paar]
                verwaist = conn.execute(f"""
                    DELETE FROM official_expenses
                    WHERE match_id = ? AND (rolle, seq) NOT IN (VALUES {platzhalter})
                """, [match_id, *werte]).rowcount

                if verwaist:
                    logger.info(
                        f"Spiel {match_id}: {verwaist} Fahrtkosten-Eintraege zu nicht mehr "
                        "angesetzten Unparteiischen entfernt"
                    )

        if own_conn:
            conn.commit()

        return match_id
    finally:
        if own_conn:
            conn.close()


def mark_missing_matches(user_id: int, seen_keys: List[str], now: Optional[str] = None) -> int:
    """
    Markiert kuenftige Ansetzungen, die im letzten Scrape nicht mehr auftauchten.

    Wichtig ist die Einschraenkung auf kuenftige Spiele: die DFBnet-Ansetzung
    ist ein rollierendes Fenster von rund 14 Tagen. Ein gespieltes Spiel faellt
    zwangslaeufig irgendwann heraus - das ist Normalfall, keine Ruecknahme.
    Ohne diese Bedingung wuerde jedes Spiel zwei Wochen nach dem Spieltag als
    "fehlend" markiert und das Flag waere wertlos.

    Verschwindet dagegen ein Spiel, das noch bevorsteht, wurde die Ansetzung
    tatsaechlich zurueckgezogen oder umbesetzt.

    Geloescht wird trotzdem nichts, damit eingetragene Kilometer nicht
    mitverschwinden. Taucht das Spiel wieder auf, raeumt upsert_match die
    Markierung weg.

    Returns:
        Anzahl neu markierter Spiele.
    """
    if not seen_keys:
        # Leerer Scrape: nichts markieren. Ein Login-Fehler oder eine
        # spielfreie Woche darf nicht die ganze Historie entwerten.
        return 0

    now = now or datetime.now(UTC).isoformat()
    today = now[:10]
    conn = get_connection()

    try:
        placeholders = ",".join("?" * len(seen_keys))
        cursor = conn.execute(f"""
            UPDATE matches SET missing_since = ?
            WHERE user_id = ? AND missing_since IS NULL
              AND datum >= ?
              AND match_key NOT IN ({placeholders})
        """, [now, user_id, today, *seen_keys])

        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def _rows_to_matches(match_rows, official_rows, expense_rows) -> List[Dict]:
    """Baut aus den drei Tabellen die Struktur, die Scraper und Generator sprechen."""
    officials_by_match: Dict[int, List[Dict]] = {}
    for row in official_rows:
        officials_by_match.setdefault(row["match_id"], []).append(dict(row))

    expenses_by_match: Dict[int, List[Dict]] = {}
    for row in expense_rows:
        expenses_by_match.setdefault(row["match_id"], []).append(dict(row))

    matches = []
    for row in match_rows:
        match = dict(row)
        officials = sorted(
            officials_by_match.get(match["id"], []),
            key=lambda o: (o["rolle"], o["seq"]),
        )

        # Flaches Dict fuer den Generator: sr_km, sra1_oevm, ...
        flat_expenses: Dict[str, Optional[float]] = {}
        for entry in expenses_by_match.get(match["id"], []):
            prefix = _expense_prefix(entry["rolle"], entry["seq"])
            if prefix:
                flat_expenses[f"{prefix}_km"] = entry["km"]
                flat_expenses[f"{prefix}_oevm"] = entry["oevm"]

        matches.append({
            **match,
            "spiel_info": {
                "anpfiff": match["anpfiff"],
                "heim_team": match["heim_team"],
                "gast_team": match["gast_team"],
                "mannschaftsart": match["mannschaftsart"],
                "spielklasse": match["spielklasse"],
                "staffel": match["staffel"],
                "spieltag": match["spieltag"],
            },
            "schiedsrichter": [
                {
                    "rolle": o["rolle"],
                    "name": o["name"],
                    "telefon": o["telefon"],
                    "email": o["email"],
                    "strasse": o["strasse"],
                    "plz_ort": o["plz_ort"],
                }
                for o in officials
            ],
            "spielstaette": {
                "name": match["staette_name"],
                "adresse": match["staette_adresse"],
                "platz_typ": match["staette_platz_typ"],
            },
            "expenses": flat_expenses or None,
        })

    return matches


def get_matches_for_user(user_id: int, include_missing: bool = True) -> List[Dict]:
    """Alle Spiele eines Users, neueste zuerst, inklusive Unparteiischer und Spesen."""
    conn = get_connection()

    try:
        where = "user_id = ?"
        if not include_missing:
            where += " AND missing_since IS NULL"

        match_rows = conn.execute(
            f"SELECT * FROM matches WHERE {where} ORDER BY datum DESC", (user_id,)
        ).fetchall()

        if not match_rows:
            return []

        ids = [row["id"] for row in match_rows]
        placeholders = ",".join("?" * len(ids))
        official_rows = conn.execute(
            f"SELECT * FROM match_officials WHERE match_id IN ({placeholders})", ids
        ).fetchall()
        expense_rows = conn.execute(
            f"SELECT * FROM official_expenses WHERE match_id IN ({placeholders})", ids
        ).fetchall()

        return _rows_to_matches(match_rows, official_rows, expense_rows)
    finally:
        conn.close()


def get_match(match_id: int) -> Optional[Dict]:
    """Ein einzelnes Spiel samt Unparteiischen und Spesen, oder None."""
    conn = get_connection()

    try:
        match_row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not match_row:
            return None

        official_rows = conn.execute(
            "SELECT * FROM match_officials WHERE match_id = ?", (match_id,)
        ).fetchall()
        expense_rows = conn.execute(
            "SELECT * FROM official_expenses WHERE match_id = ?", (match_id,)
        ).fetchall()

        return _rows_to_matches([match_row], official_rows, expense_rows)[0]
    finally:
        conn.close()


def set_official_expenses(match_id: int, expenses: Dict[str, Optional[float]]) -> None:
    """
    Speichert Fahrtkosten und OeVM fuer ein Spiel.

    Args:
        expenses: Flaches Dict aus dem Formular, z.B. {'sr_km': 42.0,
                  'sra1_oevm': 7.5}. Nur uebergebene Schluessel werden
                  angefasst - ein Teil-Update darf die anderen Rollen nicht
                  auf NULL setzen. None als Wert loescht den Eintrag.
    """
    conn = get_connection()
    now = datetime.now(UTC).isoformat()

    try:
        for rolle, seq, prefix in FORM_ROLES:
            km_key, oevm_key = f"{prefix}_km", f"{prefix}_oevm"
            if km_key not in expenses and oevm_key not in expenses:
                continue

            existing = conn.execute("""
                SELECT km, oevm FROM official_expenses
                WHERE match_id = ? AND rolle = ? AND seq = ?
            """, (match_id, rolle, seq)).fetchone()

            km = expenses.get(km_key, existing["km"] if existing else None)
            oevm = expenses.get(oevm_key, existing["oevm"] if existing else None)

            if km is None and oevm is None:
                conn.execute("""
                    DELETE FROM official_expenses
                    WHERE match_id = ? AND rolle = ? AND seq = ?
                """, (match_id, rolle, seq))
                continue

            conn.execute("""
                INSERT INTO official_expenses (match_id, rolle, seq, km, oevm, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (match_id, rolle, seq) DO UPDATE SET
                    km = excluded.km,
                    oevm = excluded.oevm,
                    updated_at = excluded.updated_at
            """, (match_id, rolle, seq, km, oevm, now))

        conn.commit()
    finally:
        conn.close()


def count_distinct_matches() -> int:
    """
    Anzahl verschiedener Spiele ueber alle User - fuer die Zahl auf der
    Startseite. Ein Spiel, das drei Unparteiische aus der Nutzerbasis leiten,
    liegt dreimal in der Tabelle und zaehlt hier trotzdem einmal: der
    match_key ist userunabhaengig.
    """
    conn = get_connection()

    try:
        row = conn.execute("SELECT COUNT(DISTINCT match_key) AS n FROM matches").fetchone()
        return row["n"] or 0
    finally:
        conn.close()
