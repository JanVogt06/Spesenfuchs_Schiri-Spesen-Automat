"""
Expenses and travel costs of the user's own matches, per season.

Counted are past assignments that were not withdrawn.
Expenses are those of the user's own role (SR or SRA rate, frozen at the
first fetch). Travel costs come from the entered kilometres and
public-transport (OeVM) amounts; where nothing is entered for the own role, they are
estimated: alone from the own place of residence to the pitch and back, by
road kilometres. The response keeps recorded and estimated separate.
"""
import time
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from db.matches import FORM_ROLES, get_matches_for_user
from db.stammdaten import get_stammdaten
from utils.eigene_spiele import STANDARD_FRIST_SEKUNDEN, Ortsuche, eigene_person, wohnadresse
from utils.fahrten import spielort_aus
from utils.routing import UMWEGFAKTOR, RoutingNichtErreichbar, entfernungen, luftlinie_m
from utils.saison_utils import saison_fuer_datum

STANDARD_KM_SATZ = 0.30


def _praefix(rolle: str, seq: int) -> Optional[str]:
    return next((p for r, s, p in FORM_ROLES if r == rolle and s == seq), None)


def _vergangene(matches: List[Dict], heute: str) -> List[Dict]:
    return [m for m in matches
            if m.get("datum") and m["datum"] != "1900-01-01" and m["datum"] < heute
            and not m.get("missing_since")]


def _euro(wert: float) -> float:
    return round(wert + 1e-9, 2)


def statistik(user_id: int, saison: Optional[str] = None, frist: Optional[float] = None,
              heute: Optional[date] = None) -> Dict:
    heute_iso = (heute or date.today()).isoformat()
    frist = frist if frist is not None else time.monotonic() + STANDARD_FRIST_SEKUNDEN

    vergangene = _vergangene(get_matches_for_user(user_id, include_missing=False), heute_iso)
    for match in vergangene:
        match["_saison"] = saison_fuer_datum(date.fromisoformat(match["datum"]))

    saisons = sorted({m["_saison"] for m in vergangene}, reverse=True)
    if saison not in saisons:
        saison = saisons[0] if saisons else None

    name = (get_stammdaten(user_id) or {}).get("name_vorname") or ""
    ortsuche = Ortsuche(frist)

    monate: Dict[str, Dict] = defaultdict(lambda: {"spiele": 0, "spesen": 0.0,
                                                   "fahrt_erfasst": 0.0, "fahrt_geschaetzt": 0.0})
    rollen: Dict[str, Dict] = defaultdict(lambda: {"spiele": 0, "spesen": 0.0})
    summe = {"spiele": 0, "ohne_rolle": 0, "ohne_satz": 0, "spesen": 0.0}
    fahrt = {"erfasst": 0.0, "erfasst_spiele": 0, "geschaetzt": 0.0, "geschaetzt_spiele": 0,
             "geschaetzt_km": 0, "ohne_schaetzung": 0, "luftlinie_spiele": 0}
    zu_schaetzen = []  # (month, km rate, place of residence, venue)

    for match in (m for m in vergangene if m["_saison"] == saison):
        person = eigene_person(match, name)
        if person is None:
            summe["ohne_rolle"] += 1
            continue

        monat = monate[match["datum"][:7]]
        summe["spiele"] += 1
        monat["spiele"] += 1
        rollen[person["rolle"]]["spiele"] += 1

        satz = match.get("sr_spesen") if person["rolle"] == "SR" else match.get("sra_spesen")
        if satz is None:
            summe["ohne_satz"] += 1
        else:
            summe["spesen"] += satz
            monat["spesen"] += satz
            rollen[person["rolle"]]["spesen"] += satz

        km_satz = match.get("km_satz") or STANDARD_KM_SATZ
        praefix = _praefix(person["rolle"], person["seq"])
        kosten = match.get("expenses") or {}
        km = kosten.get(f"{praefix}_km") if praefix else None
        oevm = kosten.get(f"{praefix}_oevm") if praefix else None

        if km is not None or oevm is not None:
            betrag = (km or 0) * km_satz + (oevm or 0)
            fahrt["erfasst"] += betrag
            fahrt["erfasst_spiele"] += 1
            monat["fahrt_erfasst"] += betrag
            continue

        adresse, ort = wohnadresse(person)
        wohnort = ortsuche.punkt(adresse, ort) if adresse else None
        platz = spielort_aus(match, ortsuche.punkt)
        if wohnort is None or platz is None:
            fahrt["ohne_schaetzung"] += 1
            continue
        zu_schaetzen.append((match["datum"][:7], km_satz, wohnort, platz))

    offen_strecken = _schaetzen(zu_schaetzen, frist, monate, fahrt)

    for monat in monate.values():
        for feld in ("spesen", "fahrt_erfasst", "fahrt_geschaetzt"):
            monat[feld] = _euro(monat[feld])

    fahrt["erfasst"] = _euro(fahrt["erfasst"])
    fahrt["geschaetzt"] = _euro(fahrt["geschaetzt"])
    return {
        "saisons": saisons,
        "saison": saison,
        "spiele": summe["spiele"],
        "ohne_rolle": summe["ohne_rolle"],
        "ohne_satz": summe["ohne_satz"],
        "spesen": _euro(summe["spesen"]),
        "fahrtkosten": fahrt,
        "gesamt": _euro(summe["spesen"] + fahrt["erfasst"] + fahrt["geschaetzt"]),
        "monate": [{"monat": k, **v} for k, v in sorted(monate.items())],
        "rollen": [{"rolle": k, "spiele": v["spiele"], "spesen": _euro(v["spesen"])}
                   for k, v in sorted(rollen.items())],
        # Not looked up yet: the frontend then asks again
        "offen": ortsuche.offen + offen_strecken,
    }


def _schaetzen(zu_schaetzen, frist, monate, fahrt) -> int:
    """Enters the estimated travel costs; returns the number of matches still open."""
    offen = 0
    nach_wohnort = defaultdict(list)
    for eintrag in zu_schaetzen:
        nach_wohnort[eintrag[2]].append(eintrag)

    for wohnort, eintraege in nach_wohnort.items():
        plaetze = list(dict.fromkeys(e[3] for e in eintraege))
        luftlinie = False
        try:
            hin = entfernungen([wohnort], plaetze, frist)
            zurueck = entfernungen(plaetze, [wohnort], frist)
            meter = {p: (hin.meter[0][i], zurueck.meter[i][0]) for i, p in enumerate(plaetze)}
        except RoutingNichtErreichbar:
            luftlinie = True
            meter = {p: (luftlinie_m(wohnort, p) * UMWEGFAKTOR,) * 2 for p in plaetze}

        for monat, km_satz, _, platz in eintraege:
            hin_m, zurueck_m = meter[platz]
            if hin_m is None or zurueck_m is None:
                offen += 1
                continue
            km = int((hin_m + zurueck_m) / 1000 + 0.5)
            betrag = km * km_satz
            fahrt["geschaetzt"] += betrag
            fahrt["geschaetzt_spiele"] += 1
            fahrt["geschaetzt_km"] += km
            fahrt["luftlinie_spiele"] += 1 if luftlinie else 0
            monate[monat]["fahrt_geschaetzt"] += betrag

    return offen
