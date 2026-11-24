"""
Liest die eigenen Ansetzungen aus der JSON-Schnittstelle der Schiriansetzung.

Die Ansetzungs-App (sria.dfbnet.org) ist eine Angular-App, die alles von
https://api.dfbnet.org/api/referee/ laedt. Statt fuer jedes Spiel drei Modals
aufzuklicken und auszulesen, stellt dieses Modul genau die Abrufe, die die App
selbst macht:

1. appointment/with-action-state - die Ansetzungen eines Zeitraums, mit dem
   kompletten Gespann samt Kontaktdaten
2. match?match-ids=...           - Anpfiff, Spieltag, Staffel, Teams, Spielstaette
3. club-team?club-team-ids=...   - die Teamnamen
4. league/<id>                   - Spielklasse und Mannschaftsart des Wettbewerbs
5. venue/query (POST, nur lesend) - Name, Adresse und Platzart der Spielstaette

Die Spielklasse kommt bewusst aus dem Wettbewerb (league) und nicht aus dem
Team: bei einem Pokal- oder Freundschaftsspiel steht dort "Kreispokal" bzw.
"Kreisfreundschaftsspiele", die Liga des Teams waere falsch. Die Werte sind
am 24.11.2026 Feld fuer Feld gegen das abgeglichen worden, was die Modals in
die Datenbank geschrieben hatten - sie sind identisch, die Schluessel der
gespeicherten Spiele bleiben also gleich.

Anmeldung, Token und erlaubte Abrufe: siehe scraper/sria_api.py.

Das Fenster "Heute +/- 2 Wochen" der Liste "Meine Spiele" ist nur die
Voreinstellung ihres Auswahlfelds. Die Schnittstelle liefert jeden Zeitraum.
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urlencode

from playwright.sync_api import Page

from scraper import sria_api
from scraper.sria_api import abruf, bloecke, iso, text as _text
from utils.logger import setup_logger

logger = setup_logger("ansetzungen")

# Ansetzungen je Seite; die Antwort ist ein blosses Array ohne Seitenangaben
_SEITE = 100
_MAX_SEITEN = 20

_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Rollen der Schnittstelle -> Rollen in der Datenbank und im Formular.
# Beobachter (OBSERVER) standen nie im Gespann-Modal und bleiben draussen.
_ROLLEN = {"REFEREE": "SR", "ASSISTANT_1": "SRA 1", "ASSISTANT_2": "SRA 2"}
_ROLLEN_FOLGE = list(_ROLLEN.values())

_PLATZARTEN = {
    "GRASS_PITCH": "Rasenplatz",
    "ARTIFICIAL_PITCH": "Kunstrasenplatz",
    "HARD_PITCH": "Hartplatz",
}


def zeitraum(heute: Optional[date] = None):
    """
    Der abgefragte Zeitraum: die laufende Saison (mindestens die letzten zwei
    Wochen, damit Anfang Juli die letzten Spiele der alten Saison nicht
    herausfallen) bis ein Jahr voraus.
    """
    heute = heute or date.today()
    saisonstart = date(heute.year if heute.month >= 7 else heute.year - 1, 7, 1)
    von = min(saisonstart, heute - timedelta(days=14))
    # Einen Tag Puffer, weil die Grenzen als UTC-Zeitpunkte gehen
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
    """Alle Rohdaten zu den Ansetzungen eines Zeitraums - je Art ein paar Abrufe."""
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
            "staetten": staetten, "wettbewerbe": wettbewerbe}


# ------------------------------------------------------------- Aufbereitung

def anpfiff_text(anstoss: Optional[str]) -> str:
    """'2026-11-14T14:00:00+01:00' -> 'Samstag · 14.11.2026 · 14:00 Uhr' (Ortszeit)."""
    if not anstoss:
        return ""
    zeit = datetime.fromisoformat(anstoss)
    return f"{_WOCHENTAGE[zeit.weekday()]} · {zeit:%d.%m.%Y} · {zeit:%H:%M} Uhr"


def _adresse(adresse: Optional[Dict]) -> str:
    adresse = adresse or {}
    ort = " ".join(t for t in (_text(adresse.get("zipCode")), _text(adresse.get("city"))) if t)
    return ", ".join(t for t in (_text(adresse.get("street")), ort) if t)


def _gespann(personen: List[Dict]) -> List[Dict]:
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
        })
    # Stabil sortiert: bei Turnieren bleibt die Reihenfolge mehrerer SR erhalten
    return sorted(gespann, key=lambda p: _ROLLEN_FOLGE.index(p["rolle"]))


def aufbereiten(ansetzung: Dict, rohdaten: Dict) -> Dict:
    """
    Eine Ansetzung in der Struktur, die die Datenbank und der Generator
    erwarten ('spiel_info', 'schiedsrichter', 'spielstaette').
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
        "schiedsrichter": _gespann(ansetzung.get("referees")),
        "spielstaette": {
            "name": _text(staette.get("name")),
            "adresse": _adresse(staette.get("address")),
            "platz_typ": _PLATZARTEN.get(staette.get("type"), ""),
        },
    }
