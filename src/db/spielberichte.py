"""
Datenbankzugriff fuer die Spielberichte und ihre angehaengten Dokumente.

Anders als bei den Saisons wird hier nicht saisonweise ersetzt, sondern je
Bericht geschrieben: ein Lauf liest nur Berichte, die neu sind oder noch
nachgetragen werden koennten (Sonderberichte kommen oft Tage spaeter). Was
DFBnet bei einem Bericht nicht mehr fuehrt - ein geloeschtes Dokument -,
verschwindet auch hier.

Die Dateien liegen unter DATA_DIR/spielberichte/<user_id>/<dfb_spiel_id>/.
Der Dateiname auf der Platte besteht nur aus DFBnet-IDs; der echte Name steht
in der Datenbank und wird erst beim Download wieder angelegt.
"""
import json
import re
import shutil
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from core.config import get_data_dir
from db.database import get_connection
from utils.logger import setup_logger

logger = setup_logger("db_spielberichte")

_SICHER = re.compile(r"[^A-Za-z0-9]")


def _benutzer_ordner(user_id: int) -> Path:
    return get_data_dir() / "spielberichte" / str(int(user_id))


def _dateipfad(user_id: int, dfb_spiel_id: str, dfb_dokument_id: str, dateiname: str) -> Path:
    """Pfad einer Dokumentdatei - nur aus IDs und einer bereinigten Endung."""
    endung = Path(dateiname or "").suffix.lstrip(".")
    endung = _SICHER.sub("", endung)[:5].lower() or "bin"
    return (
        _benutzer_ordner(user_id)
        / _SICHER.sub("", dfb_spiel_id)
        / f"{_SICHER.sub('', dfb_dokument_id)}.{endung}"
    )


def normalisiere_team(name: str) -> str:
    """Fuer den Abgleich: ohne weiche Trennstriche, Satzzeichen und Gross/Klein."""
    return re.sub(r"[\W_]+", "", (name or "").replace("­", "")).casefold()


# ------------------------------------------------------------------ Schreiben

def speichere_bericht(
    user_id: int,
    saison: str,
    zeile: Dict,
    daten: Dict,
    dateien: Dict[str, bytes],
    scraped_at: Optional[str] = None,
) -> int:
    """
    Schreibt einen Bericht samt Dokumenten.

    Args:
        zeile: die Einsatzplan-Zeile (dfb_spiel_id, datum, uhrzeit, gruppe,
               nummer, heim, gast, ergebnis)
        daten: der aufbereitete Bericht (scraper.spielberichte.aufbereiten)
        dateien: neu geladene Dokumente, dfb_dokument_id -> Inhalt. Dokumente,
                 die schon gespeichert sind, fehlen hier und bleiben stehen.

    Returns:
        id des Berichts.
    """
    scraped_at = scraped_at or datetime.now(UTC).isoformat()
    kosten = daten.get("kosten") or {}
    dfb_spiel_id = zeile["dfb_spiel_id"]

    conn = get_connection()
    geschriebene: List[Path] = []
    zu_loeschen: List[Path] = []

    try:
        conn.execute("BEGIN")
        conn.execute("""
            INSERT INTO spielberichte (
                user_id, dfb_spiel_id, saison, datum, uhrzeit, gruppe, spielnummer,
                spielkennung, heim, gast, ergebnis, fahrtkosten, spesen, daten, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, dfb_spiel_id) DO UPDATE SET
                saison = excluded.saison,
                datum = excluded.datum,
                uhrzeit = excluded.uhrzeit,
                gruppe = excluded.gruppe,
                spielnummer = excluded.spielnummer,
                spielkennung = excluded.spielkennung,
                heim = excluded.heim,
                gast = excluded.gast,
                ergebnis = excluded.ergebnis,
                fahrtkosten = excluded.fahrtkosten,
                spesen = excluded.spesen,
                daten = excluded.daten,
                scraped_at = excluded.scraped_at
        """, (
            user_id, dfb_spiel_id, saison,
            zeile.get("datum") or "1900-01-01",
            zeile.get("uhrzeit") or "",
            zeile.get("gruppe") or "",
            zeile.get("nummer") or "",
            daten.get("spielkennung") or "",
            zeile.get("heim") or daten.get("heim") or "",
            zeile.get("gast") or daten.get("gast") or "",
            zeile.get("ergebnis") or (daten.get("ergebnis") or {}).get("endstand") or "",
            kosten.get("fahrtkosten"),
            kosten.get("spesen"),
            json.dumps(daten, ensure_ascii=False),
            scraped_at,
        ))
        bericht_id = conn.execute(
            "SELECT id FROM spielberichte WHERE user_id = ? AND dfb_spiel_id = ?",
            (user_id, dfb_spiel_id),
        ).fetchone()["id"]

        vorhanden = {
            row["dfb_dokument_id"]: row["pfad"]
            for row in conn.execute(
                "SELECT dfb_dokument_id, pfad FROM spielbericht_dokumente WHERE spielbericht_id = ?",
                (bericht_id,),
            ).fetchall()
        }

        kategorien = {str(k): v for k, v in (daten.get("kategorien") or {}).items()}
        aktuell = set()

        for dokument in daten.get("dokumente") or []:
            dok_id = dokument.get("dfb_id")
            if not dok_id:
                continue
            aktuell.add(dok_id)

            if dok_id in vorhanden and dok_id not in dateien:
                continue
            if dok_id not in dateien:
                # Weder gespeichert noch geladen (Download fehlgeschlagen) -
                # der naechste Lauf versucht es wieder.
                continue

            pfad = _dateipfad(user_id, dfb_spiel_id, dok_id, dokument.get("dateiname"))
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.write_bytes(dateien[dok_id])
            geschriebene.append(pfad)

            hochgeladen = dokument.get("hochgeladen") or {}
            conn.execute("""
                INSERT INTO spielbericht_dokumente (
                    spielbericht_id, dfb_dokument_id, kategorie, dateiname, beschreibung,
                    hochgeladen_von, hochgeladen_am, groesse, pfad, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (spielbericht_id, dfb_dokument_id) DO UPDATE SET
                    kategorie = excluded.kategorie,
                    dateiname = excluded.dateiname,
                    beschreibung = excluded.beschreibung,
                    hochgeladen_von = excluded.hochgeladen_von,
                    hochgeladen_am = excluded.hochgeladen_am,
                    groesse = excluded.groesse,
                    pfad = excluded.pfad,
                    scraped_at = excluded.scraped_at
            """, (
                bericht_id, dok_id,
                kategorien.get(str(dokument.get("kategorie_id")), ""),
                dokument.get("dateiname") or f"{dok_id}.pdf",
                dokument.get("beschreibung") or "",
                hochgeladen.get("name") or "",
                hochgeladen.get("zeit") or "",
                len(dateien[dok_id]),
                str(pfad.relative_to(get_data_dir())),
                scraped_at,
            ))

        for dok_id, pfad in vorhanden.items():
            if dok_id not in aktuell:
                conn.execute(
                    "DELETE FROM spielbericht_dokumente WHERE spielbericht_id = ? AND dfb_dokument_id = ?",
                    (bericht_id, dok_id),
                )
                zu_loeschen.append(get_data_dir() / pfad)

        conn.commit()

    except Exception:
        conn.rollback()
        for pfad in geschriebene:
            pfad.unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    for pfad in zu_loeschen:
        pfad.unlink(missing_ok=True)

    return bericht_id


def setze_saison(user_id: int, saison: str, anzahl: int, fertig: bool,
                 scraped_at: Optional[str] = None) -> None:
    scraped_at = scraped_at or datetime.now(UTC).isoformat()
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO spielbericht_saisons (user_id, saison, anzahl, fertig, scraped_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id, saison) DO UPDATE SET
                anzahl = excluded.anzahl,
                fertig = excluded.fertig,
                scraped_at = excluded.scraped_at
        """, (user_id, saison, anzahl, 1 if fertig else 0, scraped_at))
        conn.commit()
    finally:
        conn.close()


def delete_spielberichte(user_id: int) -> int:
    """Loescht alle Berichte und Dokumente eines Users (Wechsel des DFBnet-Kontos)."""
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute("""
            DELETE FROM spielbericht_dokumente
            WHERE spielbericht_id IN (SELECT id FROM spielberichte WHERE user_id = ?)
        """, (user_id,))
        cursor = conn.execute("DELETE FROM spielberichte WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM spielbericht_saisons WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    shutil.rmtree(_benutzer_ordner(user_id), ignore_errors=True)
    if cursor.rowcount:
        logger.info(f"[User {user_id}] {cursor.rowcount} Spielberichte geloescht")
    return cursor.rowcount


# -------------------------------------------------------------------- Lesen

def get_fertige_saisons(user_id: int) -> Set[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT saison FROM spielbericht_saisons WHERE user_id = ? AND fertig = 1", (user_id,)
        ).fetchall()
        return {row["saison"] for row in rows}
    finally:
        conn.close()


def get_gespeicherte(user_id: int) -> Dict[str, str]:
    """dfb_spiel_id -> scraped_at aller gespeicherten Berichte."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT dfb_spiel_id, scraped_at FROM spielberichte WHERE user_id = ?", (user_id,)
        ).fetchall()
        return {row["dfb_spiel_id"]: row["scraped_at"] for row in rows}
    finally:
        conn.close()


def get_dokument_ids(user_id: int) -> Set[str]:
    """IDs der Dokumente, deren Datei schon auf der Platte liegt."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT d.dfb_dokument_id, d.pfad
            FROM spielbericht_dokumente d
            JOIN spielberichte b ON b.id = d.spielbericht_id
            WHERE b.user_id = ?
        """, (user_id,)).fetchall()
        basis = get_data_dir()
        return {row["dfb_dokument_id"] for row in rows if (basis / row["pfad"]).is_file()}
    finally:
        conn.close()


def get_index(user_id: int) -> List[Dict]:
    """
    Die Kopfzeilen aller Berichte eines Users - fuer die Zuordnung zu Saison-
    und Spesenspielen, ohne die grossen JSON-Spalten zu laden.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT b.id, b.datum, b.uhrzeit, b.heim, b.gast, b.fahrtkosten, b.spesen,
                   COUNT(d.id) AS dokumente
            FROM spielberichte b
            LEFT JOIN spielbericht_dokumente d ON d.spielbericht_id = b.id
            WHERE b.user_id = ?
            GROUP BY b.id
        """, (user_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_spielorte(user_id: int) -> List[Dict]:
    """
    Spielstaette und Ausgang je Bericht - fuer die Karte der besuchten Plaetze.
    Liest aus dem JSON nur die beiden Teile, die dafuer zaehlen.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT dfb_spiel_id, saison, datum, heim, gast, daten FROM spielberichte WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    orte = []
    for row in rows:
        try:
            daten = json.loads(row["daten"] or "{}")
        except ValueError:
            daten = {}
        ergebnis = daten.get("ergebnis") or {}
        orte.append({
            "dfb_spiel_id": row["dfb_spiel_id"],
            "saison": row["saison"],
            "datum": row["datum"],
            "heim": row["heim"],
            "gast": row["gast"],
            "spielstaette": daten.get("spielstaette") or {},
            # Ausgefallen: eine Wertung, aber kein Endstand
            "ausgefallen": bool(ergebnis.get("wertung")) and not ergebnis.get("endstand"),
        })
    return orte


# Was in den DFBnet-Modulen mal am Mannschaftsnamen steht und mal nicht:
# Altersklasse ("U19", "U18/U19"), Mannschaftsnummer ("2.", "II", "1") und
# Rechtsform ("e.V."). Der Spielbericht schreibt "SG Dynamo Dresden", die
# Saisonliste "SG Dynamo Dresden U19"; "Hertha BSC II" ist "Hertha BSC U23".
_ZUSATZ = re.compile(r"^(u\d{1,2}|i{1,3}|iv|\d{1,2}|e|v|ev)$")


def team_kern(name: str) -> str:
    """Der Vereinsname ohne Altersklasse, Mannschaftsnummer und Rechtsform."""
    text = (name or "").replace("\u00ad", "").casefold()
    woerter = [w for w in re.split(r"[\W_]+", text) if w and not _ZUSATZ.match(w)]
    return "".join(woerter)


def _gleiches_team(a: str, b: str) -> bool:
    """
    Gleicher Kern, oder der eine steckt im anderen ("Arminia Bielefeld" in
    "DSC Arminia Bielefeld"). Zu kurze Kerne zaehlen nicht - sonst passte
    "SV" auf jeden Sportverein.
    """
    ka, kb = team_kern(a), team_kern(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    kurz, lang = sorted((ka, kb), key=len)
    return len(kurz) >= 8 and kurz in lang


def uhrzeit_aus(text: str) -> str:
    """'So., 22.11.2026 13:30' / '13:30' -> '13:30', sonst ''."""
    treffer = re.search(r"(\d{1,2}):(\d{2})", text or "")
    return f"{int(treffer.group(1)):02d}:{treffer.group(2)}" if treffer else ""


class Zuordnung:
    """
    Findet zu einem Spiel (Datum, Heim, Gast, Anstoss) den passenden Bericht.

    Die Namen der Mannschaften sind in den DFBnet-Modulen nicht gleich
    geschrieben (siehe team_kern). Zugeordnet wird deshalb, wenn am selben Tag
    beide Mannschaften passen - oder eine passt UND die Anstosszeit stimmt.

    Bewusst NICHT: "der einzige Bericht an diesem Tag". Das ordnete einem
    zurueckgezogenen Spiel den Bericht des Spiels zu, das man an dem Tag
    stattdessen gepfiffen hat.
    """

    def __init__(self, index: Iterable[Dict]):
        self._nach_tag: Dict[str, List[Dict]] = {}
        for eintrag in index:
            self._nach_tag.setdefault(eintrag["datum"], []).append(eintrag)

    def finde(self, datum: str, heim: str, gast: str, uhrzeit: str = "") -> Optional[Dict]:
        kandidaten = self._nach_tag.get(datum) or []
        if not kandidaten:
            return None

        zeit = uhrzeit_aus(uhrzeit)
        zur_zeit = [k for k in kandidaten if zeit and uhrzeit_aus(k.get("uhrzeit") or "") == zeit]

        beide = [k for k in kandidaten if _gleiches_team(k["heim"], heim) and _gleiches_team(k["gast"], gast)]
        if beide:
            # Bei zwei Treffern (Hin- und Rueckspiel eines Turniertags) entscheidet die Zeit
            return next((k for k in beide if k in zur_zeit), beide[0])

        eine = [k for k in zur_zeit if _gleiches_team(k["heim"], heim) or _gleiches_team(k["gast"], gast)]
        return eine[0] if len(eine) == 1 else None


def kurzinfo(eintrag: Optional[Dict]) -> Optional[Dict]:
    """Was die Listen je Spiel vom Bericht brauchen."""
    if not eintrag:
        return None
    return {
        "id": eintrag["id"],
        "fahrtkosten": eintrag["fahrtkosten"],
        "spesen": eintrag["spesen"],
        "dokumente": eintrag["dokumente"],
    }


def get_bericht(user_id: int, bericht_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM spielberichte WHERE id = ? AND user_id = ?", (bericht_id, user_id)
        ).fetchone()
        if not row:
            return None

        bericht = dict(row)
        bericht["daten"] = json.loads(bericht["daten"] or "{}")
        dokumente = conn.execute("""
            SELECT id, dfb_dokument_id, kategorie, dateiname, beschreibung,
                   hochgeladen_von, hochgeladen_am, groesse
            FROM spielbericht_dokumente
            WHERE spielbericht_id = ?
            ORDER BY hochgeladen_am, id
        """, (bericht_id,)).fetchall()
        bericht["dokumente"] = [dict(d) for d in dokumente]
        return bericht
    finally:
        conn.close()


def get_dokument(user_id: int, bericht_id: int, dokument_id: int) -> Optional[Dict]:
    """Ein Dokument samt absolutem Pfad - nur, wenn es dem User gehoert."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT d.*
            FROM spielbericht_dokumente d
            JOIN spielberichte b ON b.id = d.spielbericht_id
            WHERE d.id = ? AND d.spielbericht_id = ? AND b.user_id = ?
        """, (dokument_id, bericht_id, user_id)).fetchone()
        if not row:
            return None

        dokument = dict(row)
        basis = get_data_dir().resolve()
        pfad = (basis / dokument["pfad"]).resolve()
        if basis not in pfad.parents:
            return None
        dokument["absolut"] = pfad
        return dokument
    finally:
        conn.close()
