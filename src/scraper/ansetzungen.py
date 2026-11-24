"""
Reads the user's own assignments (Ansetzungen) from the JSON interface of the
Schiriansetzung.

The assignment app (sria.dfbnet.org) is an Angular app that loads everything
from https://api.dfbnet.org/api/referee/. Instead of clicking open and
reading three modals for every match, this module makes exactly the requests
the app itself makes:

1. appointment/with-action-state - the assignments of a period, with the
   complete crew (Gespann) including contact data
2. match?match-ids=...           - kickoff, matchday, division (Staffel), teams, venue
3. club-team?club-team-ids=...   - the team names
4. league/<id>                   - league level and team type of the competition
5. venue/query (POST, read-only) - name, address and surface type of the venue

The league level deliberately comes from the competition (league) and not from
the team: for a cup or friendly match it says "Kreispokal" or
"Kreisfreundschaftsspiele" there, and the team's league would be wrong. On
24.11.2026 the values were compared field by field against what the modals had
written to the database - they are identical, so the keys of the stored
matches stay the same.

Login, token and allowed requests: see scraper/sria_api.py.

The "Heute +/- 2 Wochen" (today +/- 2 weeks) window of the "Meine Spiele" list
is only the default of its selection field. The interface delivers any period.
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urlencode

from playwright.sync_api import Page

from scraper import sria_api
from scraper.sria_api import abruf, bloecke, iso, text as _text
from utils.logger import setup_logger

logger = setup_logger("ansetzungen")

# Assignments per page; the response is a bare array without paging information
_SEITE = 100
_MAX_SEITEN = 20

_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Roles of the interface -> roles in the database and in the form.
# Observers (OBSERVER) were never in the crew modal and stay out.
_ROLLEN = {"REFEREE": "SR", "ASSISTANT_1": "SRA 1", "ASSISTANT_2": "SRA 2"}
_ROLLEN_FOLGE = list(_ROLLEN.values())

_PLATZARTEN = {
    "GRASS_PITCH": "Rasenplatz",
    "ARTIFICIAL_PITCH": "Kunstrasenplatz",
    "HARD_PITCH": "Hartplatz",
}


def zeitraum(heute: Optional[date] = None):
    """
    The queried period: the current season (at least the last two weeks, so
    that at the start of July the last matches of the old season do not drop
    out) up to one year ahead.
    """
    heute = heute or date.today()
    saisonstart = date(heute.year if heute.month >= 7 else heute.year - 1, 7, 1)
    von = min(saisonstart, heute - timedelta(days=14))
    # One day of buffer, because the bounds are sent as UTC timestamps
    return von - timedelta(days=1), heute + timedelta(days=365)


def hole_ansetzungen(page: Page, schiri_id: str, von: date, bis: date) -> List[Dict]:
    ansetzungen = []
    for seite in range(_MAX_SEITEN):
        query = urlencode({
            "size": _SEITE, "page": seite, "sort": "kickoff,asc",
            "from": iso(von), "until": iso(bis), "referee-id": schiri_id, "filter": "",
        })
        treffer = abruf(page, "GET", f"appointment/with-action-state?{query}") or []
        ansetzungen.extend(treffer)
        if len(treffer) < _SEITE:
            return ansetzungen

    raise RuntimeError(f"Mehr als {_SEITE * _MAX_SEITEN} Ansetzungen - Abbruch")


def hole_rohdaten(page: Page, schiri_id: str, von: date, bis: date) -> Dict:
    """All raw data for the assignments of a period - a few requests per kind."""
    ansetzungen = hole_ansetzungen(page, schiri_id, von, bis)

    teams_und_spiele = sria_api.team_namen(page, (a.get("id") for a in ansetzungen))
    spiele, teams = teams_und_spiele["spiele"], teams_und_spiele["teams"]

    staetten = {}
    for block in bloecke(s.get("venueId") for s in spiele.values()):
        for staette in abruf(page, "POST", "venue/query", {"venueIds": block}) or []:
            staetten[staette["id"]] = staette

    wettbewerbe = {}
    for liga in dict.fromkeys(s.get("leagueId") for s in spiele.values() if s.get("leagueId")):
        wettbewerbe[liga] = abruf(page, "GET", f"league/{liga}") or {}

    return {"ansetzungen": ansetzungen, "spiele": spiele, "teams": teams,
            "staetten": staetten, "wettbewerbe": wettbewerbe, "schiri_id": schiri_id}


# ------------------------------------------------------------- Processing

def anpfiff_text(anstoss: Optional[str]) -> str:
    """'2026-11-14T14:00:00+01:00' -> 'Samstag · 14.11.2026 · 14:00 Uhr' (local time)."""
    if not anstoss:
        return ""
    zeit = datetime.fromisoformat(anstoss)
    return f"{_WOCHENTAGE[zeit.weekday()]} · {zeit:%d.%m.%Y} · {zeit:%H:%M} Uhr"


def _adresse(adresse: Optional[Dict]) -> str:
    adresse = adresse or {}
    ort = " ".join(t for t in (_text(adresse.get("zipCode")), _text(adresse.get("city"))) if t)
    return ", ".join(t for t in (_text(adresse.get("street")), ort) if t)


def _koordinate(wert) -> Optional[float]:
    """Latitude or longitude from the interface; anything other than a number counts as missing."""
    if isinstance(wert, bool) or not isinstance(wert, (int, float, str)):
        return None
    try:
        zahl = float(wert)
    except ValueError:
        return None
    # An interface likes to return 0/0 instead of "unknown" - nothing lies there in Germany
    return zahl if zahl else None


def _gespann(personen: List[Dict], schiri_id: Optional[str] = None) -> List[Dict]:
    """
    The crew (Gespann) in form order. "selbst" (self) marks the user's own
    person - the user's assignment lists them with their referee ID.
    """
    gespann = []
    for person in personen or []:
        rolle = _ROLLEN.get(person.get("role"))
        if not rolle:
            continue
        gespann.append({
            "rolle": rolle,
            "name": " ".join(t for t in (_text(person.get("firstName")), _text(person.get("lastName"))) if t),
            "telefon": _text(person.get("phoneNumberMobile") or person.get("phoneNumberPrivate")
                             or person.get("phoneNumberBusiness")),
            "email": _text(person.get("email")),
            "strasse": _text(person.get("street")),
            "plz_ort": _adresse({"zipCode": person.get("zipCode"), "city": person.get("city")}),
            "selbst": bool(schiri_id) and str(person.get("id") or "") == str(schiri_id),
        })
    # Sorted stably: at tournaments the order of several referees (SR) is preserved
    return sorted(gespann, key=lambda p: _ROLLEN_FOLGE.index(p["rolle"]))


def aufbereiten(ansetzung: Dict, rohdaten: Dict) -> Dict:
    """
    An assignment in the structure that the database and the generator
    expect ('spiel_info', 'schiedsrichter', 'spielstaette').
    """
    spiel = rohdaten["spiele"].get(ansetzung["id"])
    if not spiel:
        raise RuntimeError("Spiel zur Ansetzung nicht geliefert")

    heim = rohdaten["teams"].get(spiel.get("homeTeamId")) or {}
    gast = rohdaten["teams"].get(spiel.get("guestTeamId")) or {}
    wettbewerb = rohdaten["wettbewerbe"].get(spiel.get("leagueId")) or {}
    staette = rohdaten["staetten"].get(spiel.get("venueId")) or {}

    return {
        "spiel_info": {
            "dfb_spiel_id": spiel["id"],
            "anpfiff": anpfiff_text(spiel.get("kickoff") or ansetzung.get("kickoff")),
            "heim_team": _text(heim.get("name")),
            "gast_team": _text(gast.get("name")),
            "mannschaftsart": _text(wettbewerb.get("teamTypeName")),
            "spielklasse": _text(wettbewerb.get("leagueLevelName")),
            "staffel": _text(spiel.get("divisionName")),
            "spieltag": _text(spiel.get("matchDay")),
        },
        "schiedsrichter": _gespann(ansetzung.get("referees"), rohdaten.get("schiri_id")),
        "spielstaette": {
            "name": _text(staette.get("name")),
            "adresse": _adresse(staette.get("address")),
            "platz_typ": _PLATZARTEN.get(staette.get("type"), ""),
            # The interface knows the pitch location more precisely than any
            # address search: venues often have no house number
            "lat": _koordinate((staette.get("address") or {}).get("latitude")),
            "lon": _koordinate((staette.get("address") or {}).get("longitude")),
        },
    }
