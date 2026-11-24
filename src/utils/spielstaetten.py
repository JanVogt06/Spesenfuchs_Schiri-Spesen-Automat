"""
The venues (Spielstaetten) where the user has already been on duty.

Two sources, both only with matches that are over:

- the user's own assignments (excluding withdrawn ones), with the coordinate
    from DFBnet where available;
- the match reports of all read seasons, excluding cancelled matches.

A match that appears in both (same DFBnet ID) counts once. Pitches
are merged by name and postal code - an artificial-turf pitch and a
grass pitch of the same club remain two points, the same pitch from two
sources becomes one. Future matches never appear on the map.
"""
import re
from datetime import date
from typing import Dict, List, Optional

from db.matches import get_matches_for_user
from db.season import get_eigene_rollen
from db.spielberichte import get_spielorte, team_kern
from db.stammdaten import get_stammdaten
from utils.eigene_spiele import Ortsuche, eigene_person
from utils.saison_utils import saison_fuer_datum


def _plz(adresse: str) -> str:
    treffer = re.search(r"\b\d{5}\b", adresse or "")
    return treffer.group(0) if treffer else ""


def _schluessel(name: str, adresse: str) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip().casefold()
    if name:
        return f"{name}|{_plz(adresse)}"
    return "adresse|" + re.sub(r"\s+", " ", (adresse or "")).strip().casefold()


def _rolle_aus_saison(rollen: Dict[str, List[Dict]], datum: str, heim: str) -> Optional[str]:
    kern = team_kern(heim)
    for eintrag in rollen.get(datum, []):
        if kern and team_kern(eintrag["heim"]) == kern and eintrag.get("eigene_rolle"):
            return eintrag["eigene_rolle"]
    return None


def besuchte_spielstaetten(user_id: int, frist: Optional[float] = None, heute: Optional[date] = None) -> Dict:
    heute_iso = (heute or date.today()).isoformat()
    name = (get_stammdaten(user_id) or {}).get("name_vorname") or ""

    besuche: List[Dict] = []
    gesehene_ids = set()

    for match in get_matches_for_user(user_id, include_missing=False):
        datum = match.get("datum") or ""
        if not datum or datum == "1900-01-01" or datum >= heute_iso:
            continue
        staette = match.get("spielstaette") or {}
        if not staette.get("name") and not staette.get("adresse"):
            continue
        person = eigene_person(match, name)
        if match.get("dfb_spiel_id"):
            gesehene_ids.add(match["dfb_spiel_id"])
        besuche.append({
            "name": staette.get("name") or "",
            "adresse": staette.get("adresse") or "",
            "lat": match.get("staette_lat"),
            "lon": match.get("staette_lon"),
            "spiel": {
                "datum": datum,
                "saison": saison_fuer_datum(date.fromisoformat(datum)),
                "heim": match.get("heim_team") or "",
                "gast": match.get("gast_team") or "",
                "rolle": person["rolle"] if person else None,
            },
        })

    rollen: Dict[str, List[Dict]] = {}
    for eintrag in get_eigene_rollen(user_id):
        rollen.setdefault(eintrag["datum"], []).append(eintrag)

    for bericht in get_spielorte(user_id):
        datum = bericht.get("datum") or ""
        if (bericht["dfb_spiel_id"] in gesehene_ids or bericht["ausgefallen"]
                or not datum or datum >= heute_iso):
            continue
        staette = bericht["spielstaette"]
        adresse = ", ".join(t for t in (staette.get("strasse"), staette.get("ort")) if t)
        if not staette.get("name") and not adresse:
            continue
        besuche.append({
            "name": staette.get("name") or "",
            "adresse": adresse,
            "lat": None,
            "lon": None,
            "spiel": {
                "datum": datum,
                "saison": bericht.get("saison") or saison_fuer_datum(date.fromisoformat(datum)),
                "heim": bericht.get("heim") or "",
                "gast": bericht.get("gast") or "",
                "rolle": _rolle_aus_saison(rollen, datum, bericht.get("heim") or ""),
            },
        })

    gruppen: Dict[str, List[Dict]] = {}
    for besuch in besuche:
        gruppen.setdefault(_schluessel(besuch["name"], besuch["adresse"]), []).append(besuch)

    ortsuche = Ortsuche(frist)
    orte, ohne_treffer = [], 0
    for gruppe in gruppen.values():
        mit_koordinate = next((b for b in gruppe if b["lat"] is not None and b["lon"] is not None), None)
        adresse = next((b["adresse"] for b in gruppe if b["adresse"]), "")
        if mit_koordinate:
            lat, lon, genauigkeit = mit_koordinate["lat"], mit_koordinate["lon"], "platz"
        else:
            offen_vorher = ortsuche.offen
            treffer = ortsuche.treffer(adresse) if adresse else None
            if not treffer:
                ohne_treffer += 1 if ortsuche.offen == offen_vorher else 0
                continue
            lat, lon, genauigkeit = treffer["lat"], treffer["lon"], treffer["genauigkeit"]

        spiele = sorted((b["spiel"] for b in gruppe), key=lambda s: s["datum"], reverse=True)
        orte.append({
            "name": next((b["name"] for b in gruppe if b["name"]), "") or adresse,
            "adresse": adresse,
            "lat": lat,
            "lon": lon,
            "genauigkeit": genauigkeit,
            "anzahl": len(spiele),
            "spiele": spiele,
        })

    orte.sort(key=lambda o: (-o["anzahl"], o["name"]))
    return {
        "orte": orte,
        "spiele": sum(o["anzahl"] for o in orte),
        "offen": ortsuche.offen,
        "ohne_treffer": ohne_treffer,
    }
