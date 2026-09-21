"""
Datenbankzugriff fuer die eigenen Stammdaten eines Schiedsrichters.

DFBnet fuehrt diese Daten am SR-Account, und jeder App-User hinterlegt genau
einen solchen Account - deshalb gehoert zu einem User genau eine Zeile und
user_id ist zugleich Primaerschluessel.

Die persoenlichen Felder liegen Fernet-verschluesselt in der Datenbank, wie
schon die DFBnet-Zugangsdaten. Anschrift, Geburtsdatum und Telefonnummern
stuenden sonst im Klartext in app.db. Verschluesselt
kostet das nichts: gelesen wird immer nur die eine Zeile des angemeldeten
Users, es wird nie ueber diesen Feldern gefiltert oder sortiert.
"""
import sqlite3
from datetime import datetime, UTC
from typing import Dict, Optional

from core.encryption import encrypt_credential, decrypt_credential
from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_stammdaten")

# Alle Felder, die der Scraper liefert - in Schema-Reihenfolge. Die Liste ist
# zugleich die Merge-Liste: ein leerer Wert heisst "der Scraper hat nichts
# geliefert", nicht "das Feld ist jetzt leer". Ohne diese Unterscheidung
# raeumte ein einziger Layout-Wechsel bei DFBnet den ganzen Reiter leer.
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

# Felder, die verschluesselt abgelegt werden: alles, was die Person hinter dem
# Account identifiziert oder zu ihr nach Hause fuehrt. Draussen bleibt, was
# ohnehin oeffentlich am Spiel haengt (Verein, SR-Gebiet, Qualifikation) -
# das steht so schon in der Ansetzung.
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
    Schreibt die Stammdaten eines Users - eine Zeile, die ueberschrieben wird.

    Eine Historie gibt es bewusst nicht: die Daten sollen den aktuellen Stand
    aus DFBnet spiegeln, und alte Anschriften aufzubewahren waere zusaetzliche
    Datenhaltung ohne Nutzen.

    Args:
        stammdaten: flaches Dict mit den Schluesseln aus _FELDER; fehlende
                    Schluessel werden wie leere Werte behandelt und lassen den
                    gespeicherten Wert stehen.
        scraped_at: Zeitpunkt des Abrufs (Default: jetzt)
        conn: bestehende Verbindung; ohne sie wird eine eigene geoeffnet und
              committet (gleiche Konvention wie upsert_match)
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    scraped_at = scraped_at or datetime.now(UTC).isoformat()

    values = {"user_id": user_id}
    for feld in _FELDER:
        wert = (stammdaten.get(feld) or "").strip()
        # Fernet verschluesselt Leerstrings nicht (encrypt_credential gibt ''
        # zurueck) - der NULLIF-Merge unten greift also unveraendert.
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
    Die Stammdaten eines Users im Klartext, oder None vor dem ersten Abruf.

    Laesst sich ein Feld nicht entschluesseln - etwa weil der ENCRYPTION_KEY
    gewechselt hat -, wird es leer geliefert statt den ganzen Abruf scheitern
    zu lassen: ein lueckenhafter Reiter ist besser als ein Fehler, der den
    Nutzer nichts davon sehen laesst.
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
    Loescht die Stammdaten eines Users.

    Wird beim Hinterlegen neuer DFBnet-Zugangsdaten aufgerufen. Zeigt jemand
    die App auf einen anderen DFBnet-Account, gehoeren die gespeicherten Daten
    einer anderen Person - die stuenden sonst bis zum naechsten erfolgreichen
    Abruf weiter im Reiter.

    Returns:
        Ob eine Zeile geloescht wurde.
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
