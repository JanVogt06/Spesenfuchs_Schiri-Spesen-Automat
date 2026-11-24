"""
Database access for a referee's own master data (Stammdaten).

DFBnet keeps this data on the referee (SR) account, and every app user stores exactly
one such account - therefore exactly one row belongs to a user and
user_id is at the same time the primary key.

The personal fields are stored Fernet-encrypted in the database, like
the DFBnet credentials already are. Address, date of birth and phone numbers
would otherwise sit in plain text in app.db. Encrypting them
costs nothing: only the one row of the logged-in
user is ever read, and these fields are never filtered or sorted on.
"""
import sqlite3
from datetime import datetime, UTC
from typing import Dict, Optional

from core.encryption import encrypt_credential, decrypt_credential
from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_stammdaten")

# All fields the scraper delivers - in schema order. The list is
# also the merge list: an empty value means "the scraper delivered
# nothing", not "the field is now empty". Without this distinction
# a single layout change at DFBnet would empty the whole tab.
_FELDER = [
    "name_vorname",
    "strasse",
    "plz_ort",
    "geburtsdatum",
    "email",
    "telefon_privat",
    "telefon_geschaeftlich",
    "telefon_mobil",
    "ausweisnummer",
    "ausweisgueltigkeit",
    "foto_status",
    "foto_gueltigkeit",
    "sr_gebiet",
    "schiedsrichter_seit",
    "verein",
    "fehlmonate",
    "zusatzausbildungen",
    "patensystem_am",
    "kreditor_nr",
    "debitor_nr",
    "status",
    "umsatzsteuerpflichtig",
    "fussball_de_hinweis",
    "bemerkung",
    "qmax_sr",
    "qmax_sra1",
    "qmax_sra2",
    "qmax_beobachter",
]

# Fields stored encrypted: everything that identifies the person behind the
# account or leads to their home. Left outside is what is publicly attached to the match anyway
# (club, referee region, qualification) -
# it already appears that way in the assignment.
_VERSCHLUESSELTE_FELDER = {
    "name_vorname",
    "strasse",
    "plz_ort",
    "geburtsdatum",
    "email",
    "telefon_privat",
    "telefon_geschaeftlich",
    "telefon_mobil",
    "ausweisnummer",
    "kreditor_nr",
    "debitor_nr",
    "bemerkung",
}


def upsert_stammdaten(
    user_id: int,
    stammdaten: Dict,
    scraped_at: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """
    Writes the master data of a user - one row that is overwritten.

    There is deliberately no history: the data should mirror the current state
    from DFBnet, and keeping old addresses would be additional
    data storage without benefit.

    Args:
            stammdaten: flat dict with the keys from _FELDER; missing
                                    keys are treated like empty values and leave the
                                    stored value in place.
            scraped_at: Time of the fetch (default: now)
            conn: existing connection; without it a connection of its own is opened and
                        committed (same convention as upsert_match)
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    scraped_at = scraped_at or datetime.now(UTC).isoformat()

    values = {"user_id": user_id}
    for feld in _FELDER:
        wert = (stammdaten.get(feld) or "").strip()
        # Fernet does not encrypt empty strings (encrypt_credential returns ''
        # for them) - the NULLIF merge below therefore works unchanged.
        values[feld] = encrypt_credential(wert) if feld in _VERSCHLUESSELTE_FELDER else wert

    values["first_seen_at"] = scraped_at
    values["scraped_at"] = scraped_at

    merge_sets = ",\n                ".join(
        f"{feld} = COALESCE(NULLIF(excluded.{feld}, ''), stammdaten.{feld})"
        for feld in _FELDER
    )

    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    try:
        conn.execute(f"""
            INSERT INTO stammdaten ({columns})
            VALUES ({placeholders})
            ON CONFLICT (user_id) DO UPDATE SET
                {merge_sets},
                scraped_at = excluded.scraped_at
        """, values)

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


def get_stammdaten(user_id: int) -> Optional[Dict]:
    """
    The master data of a user in plain text, or None before the first fetch.

    If a field cannot be decrypted - for example because the ENCRYPTION_KEY
    was changed -, it is returned empty instead of letting the whole fetch
    fail: a patchy tab is better than an error that lets the
    user see nothing of it.
    """
    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM stammdaten WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    daten = dict(row)

    for feld in _VERSCHLUESSELTE_FELDER:
        try:
            daten[feld] = decrypt_credential(daten.get(feld) or "")
        except Exception as e:
            logger.warning(f"[User {user_id}] Stammdaten-Feld '{feld}' nicht lesbar: {e}")
            daten[feld] = ""

    return daten


def delete_stammdaten(user_id: int) -> bool:
    """
    Deletes the master data of a user.

    Called when new DFBnet credentials are stored. If someone points
    the app at another DFBnet account, the stored data belongs
    to another person - it would otherwise stay in the tab until the next successful
    fetch.

    Returns:
            Whether a row was deleted.
    """
    conn = get_connection()

    try:
        cursor = conn.execute("DELETE FROM stammdaten WHERE user_id = ?", (user_id,))
        conn.commit()

        if cursor.rowcount:
            logger.info(f"[User {user_id}] Stammdaten geloescht")

        return cursor.rowcount > 0
    finally:
        conn.close()
