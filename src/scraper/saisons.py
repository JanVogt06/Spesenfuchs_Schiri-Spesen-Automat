"""
Season summary (tab "Spiele & Statistik") via the interface.

The "Geleitete Spiele" (officiated matches) card used to be switched per
season via a selection field, paged through, and waited out against spinners
and "headers first, then data" (see memory dfbnet-ladeverhalten). The app
fetches the same data with a few requests, and this module makes exactly
those:

- season                                    - the seasons with start and end
- appointment/with-match-details             - the officiated matches of a period
  (with goals, cards and crew; the team names come via match/club-team)
- appointment/summary                        - officiated/returned/did not
  appear, per role
- referee/<id>/exemption/summary             - training evenings (Lehrabende),
  performance test (Leistungspruefung), other creditable efforts

The result has the same form as that of the old user-interface reading, so
that main.persist_saisons and db/season.py stay unchanged. Labels and
presentation ("-" for empty, "Summe" including "Sonstiger Einsatz") come from
the app's source code (24.11.2026).
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlencode

from playwright.sync_api import Page

from scraper import sria_api
from scraper.sria_api import abruf, text
from utils.logger import setup_logger

logger = setup_logger("saisons")

# Measured on 24.11.2026: the server builds the match details slowly on the
# first request (around 32 seconds for some matches) and then caches them -
# the same request afterwards took 1.5 seconds, the whole season 2.5. If
# several not-yet-cached matches are on one page, its time limit (~60 s)
# is exceeded and it responds with 500. (That was also the cause of the empty
# table at "100 Ergebnisse pro Seite" (100 results per page), which the old
# user-interface reading sidestepped with 50/20/10.) Reading is therefore done
# in pages of 20; if one fails even on the second attempt (by then usually
# cached), it is split.
_SEITE = 20
_MAX_SPIELE = 2000

# Roles in the crew of a match row (the app's teamRole) in the app's order
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

# Rows of the assignment balance (the app's row) in the app's order
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
    """Like the app: empty and 0 as "-"."""
    return str(wert) if wert else "-"


def _zeitpunkt(wert: datetime) -> str:
    return wert.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def saison_zeitraum(saison: Dict, jetzt: datetime):
    """From season start to season end - for the current one only up to now, like the app."""
    von = f"{saison['start']}T00:00:00.000Z"
    ende = datetime.fromisoformat(f"{saison['end']}T21:59:59.999+00:00")
    return von, _zeitpunkt(min(ende, jetzt))


def angebotene_saisons(alle: List[Dict], schiedsrichter_seit: Optional[str], heute: date) -> List[Dict]:
    """
    The seasons from the one in which the person became a referee up to the
    current one - newest first, like in the app's selection field.
    """
    seit = schiedsrichter_seit or ""
    return sorted(
        (s for s in alle
         if s.get("start") and s["start"] <= heute.isoformat() and (not seit or s["end"] >= seit)),
        key=lambda s: s["start"], reverse=True,
    )


def _hole_seite(page: Page, schiri_id: str, von: str, bis: str, groesse: int, seite: int) -> List[Dict]:
    """
    One page; if it fails on the server, the same entries in smaller pages.
    The parts cover exactly the range of the page: 20 -> 2x10 -> 2x5 -> 5x1.
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
    """One row of the officiated matches in the form of the old table reading."""
    anstoss = datetime.fromisoformat(spiel["kickoff"])
    match = details.get(spiel["id"]) or {}
    heim = teams.get(match.get("homeTeamId")) or {}
    gast = teams.get(match.get("guestTeamId")) or {}

    tore = (spiel.get("goalsHome"), spiel.get("goalsGuest"))
    gespann = sorted(
        (p for p in spiel.get("referees") or [] if p.get("role") in _GESPANN),
        key=lambda p: _GESPANN_FOLGE.index(p["role"]),
    )

    # A tournament has no teams; the table then shows the name of the
    # tournament block ("..., 3. Tag, NR 1") in the home column
    heim_name = text(heim.get("name")) or text((match.get("matchBlock") or {}).get("blockName"))

    return {
        "datum_text": f"{anstoss:%d.%m.%y}, {anstoss:%H:%M}",
        "liga": text((spiel.get("league") or {}).get("name")),
        "heim": heim_name,
        "gast": text(gast.get("name")),
        # Without a result the table writes "- : -"
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
    Assignment balance and courses (Lehrgaenge) from appointment/summary and
    exemption/summary.

    Returns:
        (einsaetze, lehrgaenge) as _bilanz_auswerten used to return
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

    # The run only believes zero matches if the balance also knows of nothing
    # officiated - otherwise replace_saison would empty a season.
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
    Reads the officiated matches and the balance per season.

    Args:
        ueberspringen: seasons that are already stored completely. Completed
            seasons no longer change in DFBnet. The current season is never
            among them - it grows with every matchday.

    Returns:
        season -> {spiele, einsaetze, lehrgaenge, vollstaendig, erwartet}
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
            # Keep what was read; the rest follows on the next run
            logger.warning(f"Saisons abgebrochen bei {saison['name']}: {e}")
            break
        except Exception as e:
            logger.error(f"Saison {saison['name']} konnte nicht gelesen werden: {e}")

    return ergebnis
