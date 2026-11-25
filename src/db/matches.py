"""
Database access for matches, officials and their travel costs.

The matches used to exist only as spesen_data.json in the session folders. Here
they are read and written - in exactly the structure that the scraper
delivers and the generator expects ('spiel_info', 'schiedsrichter',
'spielstaette'), so that nothing has to be rebuilt at either end.
"""
import sqlite3
from datetime import datetime, UTC
from typing import Dict, Iterable, List, Optional

from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_matches")

# Order of the roles in the form. The template has exactly three columns;
# further officials (tournament days with several SR) are stored
# but not carried over into the document.
FORM_ROLES = [("SR", 0, "sr"), ("SRA 1", 0, "sra1"), ("SRA 2", 0, "sra2")]

# Fields that are only taken over on a re-scrape if the scraper
# actually delivered a value. On partial failures it returns empty strings
# - blind overwriting would destroy good data.
_MERGE_FIELDS = [
    "heim_team", "gast_team", "anpfiff", "mannschaftsart", "spielklasse",
    "staffel", "spieltag", "staette_name", "staette_adresse", "staette_platz_typ",
    # Numbers: NULLIF(x, '') lets them through, COALESCE keeps the old value on NULL
    "staette_lat", "staette_lon",
]

# Columns that only a later migration creates (024) - see upsert_match
_NUR_MIT_WERT = ["staette_lat", "staette_lon"]


def build_match_key(spiel_info: Dict, spielstaette: Dict, datum: str) -> str:
    """
    Builds the canonical identity of a match.

    Since November 2026 every read match brings its DFBnet ID with it
    (column dfb_spiel_id), and that is then its identity - see
    _schreibe_mit_id. This key remains for rows without an ID, for
    taking over such rows and for uniqueness per user.

    Team type and Spielklasse (league level) are part of it because the same two clubs
    can have two different assignments on the same day - for example an
    indoor tournament with G-Junioren at 09:00 and C-Junioren at 14:00. Without them
    both would collapse into one row and one of the two settlements
    would be neither visible nor retrievable.

    The kick-off time is deliberately NOT part of it: in the real data 19 of
    20 multiple occurrences are mere reschedulings of the same assignment (same
    team type and Spielklasse, kick-off shifted by 30 to 120 minutes).
    They should coincide, otherwise every rescheduling would appear twice in the
    list and the entered kilometres would hang on the outdated row.

    Tournament assignments have no teams (instead several officials in the
    role SR). For them venue and kick-off take the place of the
    teams, otherwise two tournaments on the same day would collapse into one row.
    """
    heim = (spiel_info.get("heim_team") or "").strip()
    gast = (spiel_info.get("gast_team") or "").strip()

    if heim and gast:
        art = (spiel_info.get("mannschaftsart") or "").strip()
        klasse = (spiel_info.get("spielklasse") or "").strip()
        return f"{heim}|{gast}|{datum}|{art}|{klasse}"

    staette = (spielstaette.get("name") or "").strip()
    anpfiff = (spiel_info.get("anpfiff") or "").strip()

    return f"turnier|{staette}|{anpfiff or datum}"


def _expense_prefix(rolle: str, seq: int) -> Optional[str]:
    """Role -> prefix of the form fields (sr/sra1/sra2), or None."""
    for form_rolle, form_seq, prefix in FORM_ROLES:
        if rolle == form_rolle and seq == form_seq:
            return prefix
    return None


def _merge_sets(quelle: str, values: Dict) -> str:
    # Only take over non-empty values; '' means "scraper delivered
    # nothing", not "field is now empty". Fields that do not come along at all
    # (see _NUR_MIT_WERT) stay entirely out of it.
    return ",\n                ".join(
        f"{field} = COALESCE(NULLIF({quelle}{field}, ''), matches.{field})"
        for field in _MERGE_FIELDS if field in values
    )


def _schreibe_ohne_id(conn: sqlite3.Connection, values: Dict) -> int:
    """Old way without a DFBnet ID: the match is whatever has the same match_key."""
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    conn.execute(f"""
        INSERT INTO matches ({columns})
        VALUES ({placeholders})
        ON CONFLICT (user_id, match_key) DO UPDATE SET
            {_merge_sets("excluded.", values)},
            datum = COALESCE(NULLIF(excluded.datum, '1900-01-01'), matches.datum),
            scraped_at = excluded.scraped_at,
            missing_since = NULL
    """, values)

    # Do not use lastrowid: after ON CONFLICT DO UPDATE it does not
    # reliably point to the updated row.
    return conn.execute(
        "SELECT id FROM matches WHERE user_id = ? AND match_key = ?",
        (values["user_id"], values["match_key"]),
    ).fetchone()["id"]


def _freier_key(conn: sqlite3.Connection, user_id: int, match_key: str,
                dfb_spiel_id: str, eigene_id: Optional[int]) -> str:
    """
    The match_key for a match with an ID. If the key already belongs to
    another row - another DFBnet match with the same teams, date and
    class, or a legacy row after a rescheduling - the ID is appended.
    The uniqueness (user_id, match_key) is thus preserved.
    """
    belegt = conn.execute(
        "SELECT 1 FROM matches WHERE user_id = ? AND match_key = ? AND id IS NOT ?",
        (user_id, match_key, eigene_id),
    ).fetchone()
    return f"{match_key}|{dfb_spiel_id}" if belegt else match_key


def _schreibe_mit_id(conn: sqlite3.Connection, values: Dict, dfb_spiel_id: str) -> int:
    """
    The DFBnet ID is the identity of the match. It is searched for first,
    then for a row from the time before the IDs with the same match_key -
    that one gets the ID and from then on is this match. A rescheduling, even to
    another day, thus stays in the same row including travel costs.
    """
    user_id = values["user_id"]

    zeile = conn.execute(
        "SELECT id FROM matches WHERE user_id = ? AND dfb_spiel_id = ?",
        (user_id, dfb_spiel_id),
    ).fetchone() or conn.execute(
        "SELECT id FROM matches WHERE user_id = ? AND match_key = ? AND dfb_spiel_id IS NULL",
        (user_id, values["match_key"]),
    ).fetchone()

    if zeile is None:
        neu = {**values, "dfb_spiel_id": dfb_spiel_id,
               "match_key": _freier_key(conn, user_id, values["match_key"], dfb_spiel_id, None)}
        columns = ", ".join(neu)
        placeholders = ", ".join(f":{name}" for name in neu)
        return conn.execute(f"INSERT INTO matches ({columns}) VALUES ({placeholders})", neu).lastrowid

    match_id = zeile["id"]
    conn.execute(f"""
        UPDATE matches SET
            {_merge_sets(":", values)},
            match_key = :match_key,
            dfb_spiel_id = :dfb_spiel_id,
            datum = COALESCE(NULLIF(:datum, '1900-01-01'), matches.datum),
            scraped_at = :scraped_at,
            missing_since = NULL
        WHERE id = :id
    """, {**values, "id": match_id, "dfb_spiel_id": dfb_spiel_id,
          "match_key": _freier_key(conn, user_id, values["match_key"], dfb_spiel_id, match_id)})
    return match_id


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
    Creates a match or updates it and replaces the officials.

    Two things are deliberately NOT overwritten if the match already
    exists:

    - the frozen expense rates and the km rate. They apply from the first
        scrape on, so that a later change of the expense regulations does not rewrite a settlement
        that has already been submitted retroactively.
    - empty fields from a partial failure of the scraper (see _MERGE_FIELDS).

    The recorded travel costs hang on (match_id, rolle, seq) in a
    table of their own and survive the replacement of the officials.

    If the match brings a DFBnet ID (spiel_info['dfb_spiel_id']), it is
    the identity; otherwise the match_key (see _schreibe_mit_id).

    Returns:
            The ID of the match.
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
        "staette_lat": spielstaette.get("lat"),
        "staette_lon": spielstaette.get("lon"),
        "sr_spesen": sr_spesen,
        "sra_spesen": sra_spesen,
        "km_satz": km_satz,
        "first_seen_at": scraped_at,
        "scraped_at": scraped_at,
    }

    # Write columns of newer migrations only if there is a value.
    # Migration 006 creates matches from legacy data with exactly this function -
    # against a schema in which these columns do not exist yet.
    for spalte in _NUR_MIT_WERT:
        if values[spalte] is None:
            del values[spalte]

    dfb_spiel_id = (spiel_info.get("dfb_spiel_id") or "").strip()

    try:
        if dfb_spiel_id:
            match_id = _schreibe_mit_id(conn, values, dfb_spiel_id)
        else:
            match_id = _schreibe_ohne_id(conn, values)

        # Replace the snapshot of the officials - but only if the
        # scrape delivered some. Otherwise the document would be nameless.
        if schiedsrichter:
            conn.execute("DELETE FROM match_officials WHERE match_id = ?", (match_id,))

            seq_per_rolle: Dict[str, int] = {}
            for person in schiedsrichter:
                rolle = (person.get("rolle") or "").strip() or "SR"
                seq = seq_per_rolle.get(rolle, 0)
                seq_per_rolle[rolle] = seq + 1

                zeile = {
                    "match_id": match_id, "rolle": rolle, "seq": seq,
                    "name": person.get("name") or "",
                    "telefon": person.get("telefon") or "",
                    "email": person.get("email") or "",
                    "strasse": person.get("strasse") or "",
                    "plz_ort": person.get("plz_ort") or "",
                }
                # ist_selbst defaults to 0; as above, only write if it matters
                if person.get("selbst"):
                    zeile["ist_selbst"] = 1
                conn.execute(
                    f"INSERT INTO match_officials ({', '.join(zeile)}) "
                    f"VALUES ({', '.join(':' + k for k in zeile)})",
                    zeile,
                )

            # Recorded travel costs are deliberately NOT touched here, not even
            # for roles missing from this scrape. A shorter
            # list can also be a read error (formerly an accumulated
            # modal) without anything having changed in the assignment - deleting would then
            # destroy the user's entries. Values belonging to a role that is no longer
            # occupied are instead hidden when reading
            # (see _rows_to_matches) and reappear
            # when the role comes back.

        if own_conn:
            conn.commit()

        return match_id
    finally:
        if own_conn:
            conn.close()


def mark_missing_matches(user_id: int, seen_keys: List[str], now: Optional[str] = None,
                         seen_ids: Iterable[int] = (), ab: Optional[str] = None) -> int:
    """
    Marks assignments that no longer appeared in the last scrape.

    By default only future ones (see below). Since the scraper reads the
    whole current season through the referee API, every stored match from
    the start of that period on must be in the result - ab is that first
    day. A match before today that is missing there was withdrawn or
    re-staffed before it was played (a returned match, a swap on the same
    day) and must not count as officiated.

    The restriction to future matches is important: the fetch covers only
    the current season (scraper/ansetzungen.zeitraum). A played
    match inevitably drops out at some point - that is normal, not
    a withdrawal. Without this condition every match would be marked
    "missing" at the season change and the flag would be worthless. (Until November 2026 the
    scraper read the "Meine Spiele" list with its window of about 14 days;
    that is where the rule comes from.)

    If, by contrast, a match that is still upcoming disappears, the assignment was
    actually withdrawn or re-staffed.

    Nothing is deleted anyway, so that entered kilometres do not
    disappear with it. If the match reappears, upsert_match clears the
    marker.

    Args:
            seen_keys: match_keys from the scrape (old way)
            seen_ids: row IDs that upsert_match returned. Since matches with a
                    DFBnet ID stay in their row even when the key changes,
                    this is the reliable way.

    Returns:
            Number of newly marked matches.
    """
    seen_keys = list(seen_keys or [])
    seen_ids = [int(i) for i in seen_ids or []]
    if not seen_keys and not seen_ids:
        # Empty scrape: mark nothing. A login error or a week
        # without matches must not devalue the whole history.
        return 0

    now = now or datetime.now(UTC).isoformat()
    # Lower date bound: today, or the start of the fully read period
    untergrenze = min(ab, now[:10]) if ab else now[:10]
    conn = get_connection()

    try:
        keys = ",".join("?" * len(seen_keys))
        ids = ",".join("?" * len(seen_ids))
        cursor = conn.execute(f"""
            UPDATE matches SET missing_since = ?
            WHERE user_id = ? AND missing_since IS NULL
              AND datum >= ?
              AND match_key NOT IN ({keys})
              AND id NOT IN ({ids})
        """, [now, user_id, untergrenze, *seen_keys, *seen_ids])

        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def _rows_to_matches(match_rows, official_rows, expense_rows) -> List[Dict]:
    """Builds from the three tables the structure that scraper and generator speak."""
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

        # Flat dict for the generator: sr_km, sra1_oevm, ...
        #
        # Only roles that are currently occupied. Recorded values for a
        # withdrawn assistant stay in the database (a
        # scrape must not destroy user input), but belong neither in
        # the display nor in the document. If the role comes back, the value is
        # there again.
        besetzte_rollen = {(o["rolle"], o["seq"]) for o in officials if o.get("name")}

        flat_expenses: Dict[str, Optional[float]] = {}
        for entry in expenses_by_match.get(match["id"], []):
            if (entry["rolle"], entry["seq"]) not in besetzte_rollen:
                continue
            prefix = _expense_prefix(entry["rolle"], entry["seq"])
            if prefix:
                flat_expenses[f"{prefix}_km"] = entry["km"]
                flat_expenses[f"{prefix}_oevm"] = entry["oevm"]

        # The user's own row in the crew, as the assignment marked it.
        # Deliberately not in "schiedsrichter": the frontend displays every
        # field of a person.
        selbst = next(({"rolle": o["rolle"], "seq": o["seq"]} for o in officials if o.get("ist_selbst")), None)

        matches.append({
            **match,
            "selbst": selbst,
            "spiel_info": {
                "anpfiff": match["anpfiff"],
                "heim_team": match["heim_team"],
                "gast_team": match["gast_team"],
                "mannschaftsart": match["mannschaftsart"],
                "spielklasse": match["spielklasse"],
                "staffel": match["staffel"],
                "spieltag": match["spieltag"],
                "dfb_spiel_id": match.get("dfb_spiel_id") or "",
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
    """All matches of a user, newest first, including officials and expenses."""
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
    """A single match including officials and expenses, or None."""
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
    Stores travel costs and public transport (OeVM) for a match.

    Args:
            expenses: Flat dict from the form, e.g. {'sr_km': 42.0,
                                'sra1_oevm': 7.5}. Only passed keys are
                                touched - a partial update must not set the other roles
                                to NULL. None as a value deletes the entry.
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
    Number of distinct matches across all users - for the number on the
    start page. A match refereed by three officials from the user base
    lies in the table three times and still counts once here: the
    match_key is user-independent.
    """
    conn = get_connection()

    try:
        row = conn.execute("SELECT COUNT(DISTINCT match_key) AS n FROM matches").fetchone()
        return row["n"] or 0
    finally:
        conn.close()


def ergaenze_offene_saetze() -> int:
    """
    Fills in expense rates that could not yet be determined while scraping.

    For cup and friendly matches in the men's (Herren) category the rate depends on the
    Spielklasse of the participating clubs. That is in the league tables, and those
    are only filled nightly - a match assigned in July
    may not yet have had a table to look up at that point.
    A promotion or relegation may likewise only deliver the answer later.

    Only rows WITHOUT a rate are touched. A value frozen once stays
    as it is - it may appear in a settlement that has already been submitted. This
    function fills gaps, it does not correct.

    Returns:
            Number of matches filled in.
    """
    from generator.spesen_calculator import calculate_spesen

    conn = get_connection()

    try:
        offen = conn.execute(
            """
            SELECT id, spielklasse, mannschaftsart, staffel, heim_team, gast_team
            FROM matches
            WHERE sr_spesen IS NULL AND mannschaftsart = 'Herren' AND heim_team != ''
              AND (lower(spielklasse) LIKE '%pokal%' OR lower(spielklasse) LIKE '%freundschaft%')
            """
        ).fetchall()

        ergaenzt = 0
        for zeile in offen:
            sr_spesen, sra_spesen = calculate_spesen(
                zeile["spielklasse"] or "", zeile["mannschaftsart"] or "",
                zeile["staffel"] or "", zeile["heim_team"] or "", zeile["gast_team"] or "",
            )
            if sr_spesen is None:
                continue

            conn.execute(
                "UPDATE matches SET sr_spesen = ?, sra_spesen = ? WHERE id = ?",
                (sr_spesen, sra_spesen, zeile["id"]),
            )
            ergaenzt += 1

        conn.commit()
    finally:
        conn.close()

    if ergaenzt:
        logger.info(f"Spesensätze nachgetragen: {ergaenzt} Pokal-/Freundschaftsspiele")

    return ergaenzt


def setze_spielnummern(user_id: int, eintraege: Iterable[Dict]) -> int:
    """
    Enters the match identifier (e.g. "659000082") for a user's matches.

    The assignment interface does not know it; it comes from the
    duty roster of the match reports. There only past matches with a
    report carry a link and thus the DFBnet ID - future ones are matched via day,
    teams and kick-off, by the same rule as the
    reports in the match list (db.spielberichte.Zuordnung).

    Args:
            eintraege: each {"spielkennung", "dfb_spiel_id" (or None), "datum",
                    "uhrzeit", "heim", "gast"}

    Returns:
            Number of matches whose Spielkennung was newly set or changed.
    """
    from db.spielberichte import Zuordnung

    conn = get_connection()
    geaendert = 0
    try:
        zeilen = [dict(z) for z in conn.execute(
            "SELECT id, dfb_spiel_id, datum, anpfiff, heim_team, gast_team, spielnummer "
            "FROM matches WHERE user_id = ?", (user_id,),
        )]
        nach_id = {z["dfb_spiel_id"]: z for z in zeilen if z["dfb_spiel_id"]}
        zuordnung = Zuordnung(
            {**z, "heim": z["heim_team"], "gast": z["gast_team"], "uhrzeit": z["anpfiff"]}
            for z in zeilen if z["heim_team"] and z["gast_team"]
        )

        for eintrag in eintraege:
            kennung = (eintrag.get("spielkennung") or "").strip()
            if not kennung:
                continue

            zeile = nach_id.get(eintrag.get("dfb_spiel_id") or "")
            if zeile is None and eintrag.get("datum") and eintrag.get("heim"):
                zeile = zuordnung.finde(eintrag["datum"], eintrag["heim"],
                                        eintrag.get("gast") or "", eintrag.get("uhrzeit") or "")
                # A row with a different ID is a different match
                if zeile and zeile["dfb_spiel_id"] and eintrag.get("dfb_spiel_id") \
                        and zeile["dfb_spiel_id"] != eintrag["dfb_spiel_id"]:
                    zeile = None

            if zeile is not None and zeile["spielnummer"] != kennung:
                conn.execute("UPDATE matches SET spielnummer = ? WHERE id = ?", (kennung, zeile["id"]))
                zeile["spielnummer"] = kennung
                geaendert += 1

        conn.commit()
        return geaendert
    finally:
        conn.close()
