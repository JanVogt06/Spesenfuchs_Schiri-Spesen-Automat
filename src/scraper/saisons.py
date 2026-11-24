"""
Saisonzusammenfassung (Reiter "Spiele & Statistik") ueber die Schnittstelle.

Frueher wurde die Karte "Geleitete Spiele" je Saison per Auswahlfeld
umgeschaltet, geblaettert und gegen Spinner und "erst Kopfzeilen, dann
Daten" abgewartet (siehe Memory dfbnet-ladeverhalten). Die App holt dieselben
Daten mit wenigen Abrufen, und genau die stellt dieses Modul:

- season                                    - die Saisons mit Start und Ende
- appointment/with-match-details             - die geleiteten Spiele eines Zeitraums
  (mit Toren, Karten und Gespann; die Teamnamen kommen ueber match/club-team)
- appointment/summary                        - Geleitet/Zurueckgegeben/Nicht
  angetreten je Rolle
- referee/<id>/exemption/summary             - Lehrabende, Leistungspruefung,
  sonstige anrechenbare Einsaetze

Das Ergebnis hat dieselbe Form wie das der alten Oberflaechen-Lesung, damit
main.persist_saisons und db/season.py unveraendert bleiben. Beschriftungen
und Darstellung ("-" fuer leer, "Summe" inklusive "Sonstiger Einsatz") stammen
aus dem Quelltext der App (24.11.2026).
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlencode

from playwright.sync_api import Page

from scraper import sria_api
from scraper.sria_api import abruf, text
from utils.logger import setup_logger

logger = setup_logger("saisons")

# Am 24.11.2026 gemessen: der Server baut die Spieldetails beim ersten Abruf
# langsam auf (rund 32 Sekunden fuer manche Spiele) und cacht sie dann -
# derselbe Abruf kam danach in 1,5 Sekunden, die ganze Saison in 2,5. Liegen
# mehrere noch ungecachte Spiele auf einer Seite, reisst sein Zeitlimit
# (~60 s) und er antwortet mit 500. (Daher kam auch die leere Tabelle bei
# "100 Ergebnisse pro Seite", gegen die die alte Oberflaechen-Lesung auf
# 50/20/10 auswich.) Gelesen wird deshalb in 20er-Seiten; scheitert eine
# auch im zweiten Versuch (dann meist schon gecacht), wird sie geteilt.
_SEITE = 20
_MAX_SPIELE = 2000

# Rollen im Gespann einer Spielzeile (teamRole der App) in deren Reihenfolge
_GESPANN = {
    "REFEREE": "SR",
    "ASSISTANT_1": "SRA 1",
    "ASSISTANT_2": "SRA 2",
    "FOURTH_OFFICIAL": "4. Off",
    "OBSERVER": "Beo.",
    "COACH": "Coach",
    "MENTOR": "Pate",
    "VIDEO_ASSISTANT_REFEREE_1": "VA",
    "VIDEO_ASSISTANT_REFEREE_2": "AVA",
    "VIDEO_ASSISTANT_REFEREE_COACH": "VAC",
}
_GESPANN_FOLGE = list(_GESPANN)

# Zeilen der Einsatzbilanz (row der App) in deren Reihenfolge
_BILANZ = [
    ("referee", "SR"),
    ("assistant1", "SRA 1"),
    ("assistant2", "SRA 2"),
    ("fourthOfficial", "4. Off."),
    ("observer", "Beo"),
    ("videoAssistant1", "VA"),
    ("videoAssistant2", "AVA"),
    ("videoAssistantCoach", "VAC"),
    ("coach", "Coach"),
    ("mentor", "Pate"),
]


def _zelle(wert) -> str:
    """Wie die App: leer und 0 als "-"."""
    return str(wert) if wert else "-"


def _zeitpunkt(wert: datetime) -> str:
    return wert.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def saison_zeitraum(saison: Dict, jetzt: datetime):
    """Von Saisonbeginn bis Saisonende - fuer die laufende nur bis jetzt, wie die App."""
    von = f"{saison['start']}T00:00:00.000Z"
    ende = datetime.fromisoformat(f"{saison['end']}T21:59:59.999+00:00")
    return von, _zeitpunkt(min(ende, jetzt))


def angebotene_saisons(alle: List[Dict], schiedsrichter_seit: Optional[str], heute: date) -> List[Dict]:
    """
    Die Saisons ab der, in der man Schiedsrichter wurde, bis zur laufenden -
    neueste zuerst, wie im Auswahlfeld der App.
    """
    seit = schiedsrichter_seit or ""
    return sorted(
        (s for s in alle
         if s.get("start") and s["start"] <= heute.isoformat() and (not seit or s["end"] >= seit)),
        key=lambda s: s["start"], reverse=True,
    )


def _hole_seite(page: Page, schiri_id: str, von: str, bis: str, groesse: int, seite: int) -> List[Dict]:
    """
    Eine Seite; scheitert sie am Server, dieselben Eintraege in kleineren
    Seiten. Die Teile decken genau den Bereich der Seite ab: 20 -> 2x10 ->
    2x5 -> 5x1.
    """
    query = urlencode({"size": groesse, "page": seite, "sort": "kickoff,desc",
                       "from": von, "until": bis, "referee-id": schiri_id})
    try:
        return abruf(page, "GET", f"appointment/with-match-details?{query}") or []
    except sria_api.Serverfehler:
        if groesse == 1:
            raise
        teile = 2 if groesse % 2 == 0 else groesse
        klein = groesse // teile
        logger.info(f"Seite {seite} ({groesse}) scheitert am Server - lese sie in {teile} Teilen")
        ergebnis = []
        for teil in range(teile):
            treffer = _hole_seite(page, schiri_id, von, bis, klein, seite * teile + teil)
            ergebnis.extend(treffer)
            if len(treffer) < klein:
                break
        return ergebnis


def _hole_spiele(page: Page, schiri_id: str, von: str, bis: str) -> List[Dict]:
    spiele = []
    for seite in range(_MAX_SPIELE // _SEITE):
        treffer = _hole_seite(page, schiri_id, von, bis, _SEITE, seite)
        spiele.extend(treffer)
        if len(treffer) < _SEITE:
            return spiele
    raise RuntimeError(f"Mehr als {_MAX_SPIELE} Spiele in einer Saison - Abbruch")


def spielzeile(spiel: Dict, details: Dict, teams: Dict, schiri_id: str) -> Dict:
    """Eine Zeile der geleiteten Spiele in der Form der alten Tabellen-Lesung."""
    anstoss = datetime.fromisoformat(spiel["kickoff"])
    match = details.get(spiel["id"]) or {}
    heim = teams.get(match.get("homeTeamId")) or {}
    gast = teams.get(match.get("guestTeamId")) or {}

    tore = (spiel.get("goalsHome"), spiel.get("goalsGuest"))
    gespann = sorted(
        (p for p in spiel.get("referees") or [] if p.get("role") in _GESPANN),
        key=lambda p: _GESPANN_FOLGE.index(p["role"]),
    )

    # Ein Turnier hat keine Teams; die Tabelle zeigt dann den Namen des
    # Turnierblocks ("..., 3. Tag, NR 1") in der Heim-Spalte
    heim_name = text(heim.get("name")) or text((match.get("matchBlock") or {}).get("blockName"))

    return {
        "datum_text": f"{anstoss:%d.%m.%y}, {anstoss:%H:%M}",
        "liga": text((spiel.get("league") or {}).get("name")),
        "heim": heim_name,
        "gast": text(gast.get("name")),
        # Ohne Ergebnis schreibt die Tabelle "- : -"
        "ergebnis": " : ".join("-" if t is None else str(t) for t in tore),
        "heim_gelb": spiel.get("yellowCardsHome"),
        "heim_gelbrot": spiel.get("yellowRedCardsHome"),
        "heim_rot": spiel.get("redCardsHome"),
        "gast_gelb": spiel.get("yellowCardsGuest"),
        "gast_gelbrot": spiel.get("yellowRedCardsGuest"),
        "gast_rot": spiel.get("redCardsGuest"),
        "gespann": [
            {
                "rolle": _GESPANN[p["role"]],
                "name": " ".join(t for t in (text(p.get("firstName")), text(p.get("lastName"))) if t),
                "selbst": p.get("id") == schiri_id,
            }
            for p in gespann
        ],
    }


def bilanz(summe: Dict, befreiung: Dict):
    """
    Einsatzbilanz und Lehrgaenge aus appointment/summary und exemption/summary.

    Returns:
        (einsaetze, lehrgaenge) wie frueher _bilanz_auswerten
    """
    summe = summe or {}
    befreiung = befreiung or {}
    einsaetze = []
    gesamt = {"officiated": 0, "returned": 0, "notAppeared": 0}

    for schluessel, rolle in _BILANZ:
        werte = summe.get(schluessel) or {}
        for feld in gesamt:
            gesamt[feld] += werte.get(feld) or 0
        einsaetze.append({
            "rolle": rolle,
            "geleitet": _zelle(werte.get("officiated")),
            "zurueckgegeben": _zelle(werte.get("returned")),
            "nicht_angetreten": _zelle(werte.get("notAppeared")),
        })

    sonstige = befreiung.get("otherEffortsCreditable") or 0
    einsaetze.append({"rolle": "Sonstiger Einsatz", "geleitet": _zelle(sonstige),
                      "zurueckgegeben": "", "nicht_angetreten": ""})
    einsaetze.append({
        "rolle": "Summe",
        "geleitet": _zelle(gesamt["officiated"] + sonstige),
        "zurueckgegeben": _zelle(gesamt["returned"]),
        "nicht_angetreten": _zelle(gesamt["notAppeared"]),
    })

    lehrgaenge = {
        "lehrabend": _zelle(befreiung.get("trainingCoursesCreditable")),
        "lehrabend_online": _zelle(befreiung.get("trainingCoursesOnlineCreditable")),
        "leistungspruefung": _zelle(befreiung.get("performanceTests")),
    }
    return einsaetze, lehrgaenge


def lies_saison(page: Page, schiri_id: str, saison: Dict, jetzt: datetime) -> Dict:
    von, bis = saison_zeitraum(saison, jetzt)

    roh = _hole_spiele(page, schiri_id, von, bis)
    namen = sria_api.team_namen(page, (s["id"] for s in roh))
    zeilen = [spielzeile(s, namen["spiele"], namen["teams"], schiri_id) for s in roh]

    zeitraum = urlencode({"from": von, "until": bis})
    summe = abruf(page, "GET", f"appointment/summary?referee-id={schiri_id}&{zeitraum}")
    befreiung = abruf(page, "GET", f"referee/{schiri_id}/exemption/summary?{zeitraum}")
    einsaetze, lehrgaenge = bilanz(summe, befreiung)

    # Null Spiele glaubt der Lauf nur, wenn auch die Bilanz nichts Geleitetes
    # kennt - sonst wuerde replace_saison eine Saison leeren.
    geleitet = einsaetze[-1]["geleitet"]
    vollstaendig = bool(zeilen) or geleitet == "-"
    if not vollstaendig:
        logger.warning(f"Saison {saison['name']}: keine Spiele, laut Bilanz aber {geleitet} geleitet")

    return {
        "spiele": zeilen,
        "einsaetze": einsaetze,
        "lehrgaenge": lehrgaenge,
        "vollstaendig": vollstaendig,
        "erwartet": len(zeilen),
    }


def lies_saisons(page: Page, schiri_id: str, ueberspringen=None, progress_callback=None,
                 jetzt: Optional[datetime] = None) -> Dict[str, Dict]:
    """
    Liest die geleiteten Spiele und die Bilanz je Saison.

    Args:
        ueberspringen: Saisons, die bereits vollstaendig gespeichert sind.
            Abgeschlossene Saisons aendern sich bei DFBnet nicht mehr. Die
            laufende Saison gehoert nie dazu - sie waechst mit jedem Spieltag.

    Returns:
        saison -> {spiele, einsaetze, lehrgaenge, vollstaendig, erwartet}
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    ueberspringen = set(ueberspringen or ())

    schiri = abruf(page, "GET", f"referee/{schiri_id}") or {}
    saisons = angebotene_saisons(abruf(page, "GET", "season") or [],
                                 schiri.get("refereeSince"), jetzt.date())
    if saisons:
        ueberspringen.discard(saisons[0]["name"])

    zu_lesen = [s for s in saisons if s["name"] not in ueberspringen]
    logger.info(f"Saisons: {[s['name'] for s in saisons]}, zu lesen: {[s['name'] for s in zu_lesen]}")

    ergebnis = {}
    for nummer, saison in enumerate(zu_lesen, start=1):
        if progress_callback:
            progress_callback(nummer, len(zu_lesen), f"Saison {saison['name']} ({nummer}/{len(zu_lesen)})")
        try:
            ergebnis[saison["name"]] = lies_saison(page, schiri_id, saison, jetzt)
            logger.info(f"✓ Saison {saison['name']}: {len(ergebnis[saison['name']]['spiele'])} Spiele")
        except sria_api.SitzungAbgelaufen as e:
            # Das Gelesene behalten; der Rest kommt beim naechsten Lauf
            logger.warning(f"Saisons abgebrochen bei {saison['name']}: {e}")
            break
        except Exception as e:
            logger.error(f"Saison {saison['name']} konnte nicht gelesen werden: {e}")

    return ergebnis
