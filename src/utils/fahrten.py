"""
Mileage suggestions for the travel costs of a refereeing crew.

Three ways of getting to the match are worked out:

- Everyone drives alone: home -> venue -> home.
- Pick-ups: one person drives and collects the others at their homes on
  the way, dropping them off in reverse order on the way back. The whole
  distance is claimed by the driver; passengers enter 0 km.
- Meeting points: one person drives, the others drive their own cars to a
  meeting point on the driver's way and continue together from there. Each
  person claims what they drove themselves - the driver the whole trip,
  the others the trip to the meeting point and back.

Every split of the crew into cars is evaluated, each car with the cheapest
driver and the cheapest pick-up order or meeting point. Suggested are the
splits that save kilometres compared to "everyone alone".

In kilometres a pick-up is never longer than a meeting point on the way
(triangle inequality: the driver's detour to a home is at most the
passenger's trip to the road and back). A meeting point pays off in time
instead - the driver stays on the main road. So the best meeting-point
variant is always offered next to the best pick-ups, even if it is a few
kilometres longer, as long as it still saves compared to driving alone.

Candidate meeting points are spread along the straight line between a
driver's home and the venue; the route planner snaps each of them to the
nearest road.

All values cover the round trip and are rounded to whole kilometres - which
is what the expense form asks for.
"""
import math
from itertools import permutations
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from db.matches import FORM_ROLES
from utils.geocoder import GeocoderNichtErreichbar, geocode, ortsname
from utils.logger import setup_logger
from utils.routing import UMWEGFAKTOR, RoutingNichtErreichbar, entfernungen, luftlinie_m, runden

logger = setup_logger("fahrten")

# Index 0 is the venue, 1..n the homes in the order of the persons; anything
# above that is a candidate meeting point
Weg = Callable[[int, int], Optional[float]]

MAX_VORSCHLAEGE = 3

# Candidate meeting points: roughly one every few kilometres on the way, but
# never more than this many per driver (each one costs table cells)
TREFFPUNKT_ABSTAND_KM = 4
MAX_TREFFPUNKTE_JE_FAHRER = 10


def _km(meter: float) -> int:
    """Whole kilometres, rounded half up (round() would round 0.5 to even)."""
    return int(meter / 1000 + 0.5)


def _teilungen(elemente: List[int]) -> List[List[List[int]]]:
    """All splits of a set into non-empty groups (Bell number; three persons at most here)."""
    if not elemente:
        return [[]]
    erstes, rest = elemente[0], elemente[1:]
    ergebnis = []
    for teilung in _teilungen(rest):
        ergebnis.append([[erstes]] + teilung)
        for i in range(len(teilung)):
            ergebnis.append(teilung[:i] + [[erstes] + teilung[i]] + teilung[i + 1:])
    return ergebnis


def _hin_und_zurueck(weg: Weg, a: int, b: int) -> Optional[float]:
    hin, zurueck = weg(a, b), weg(b, a)
    return None if hin is None or zurueck is None else hin + zurueck


def _beste_abholung(gruppe: List[int], weg: Weg) -> Optional[Dict]:
    """
    Cheapest driver and pick-up order for a group. Passengers drive nothing.
    None if a required leg is unknown.
    """
    beste = None
    for fahrer in gruppe:
        andere = [p for p in gruppe if p != fahrer]
        for reihenfolge in permutations(andere):
            stationen = [fahrer, *reihenfolge, 0]
            hin = [weg(a, b) for a, b in zip(stationen, stationen[1:])]
            zurueck = [weg(b, a) for a, b in zip(stationen, stationen[1:])]
            if any(m is None for m in hin + zurueck):
                continue
            meter = sum(hin) + sum(zurueck)
            if beste is None or meter < beste["gesamt_m"]:
                beste = {"fahrer": fahrer, "mitfahrer": list(reihenfolge), "treffpunkt": None,
                         "meter": {fahrer: meter, **{p: 0.0 for p in reihenfolge}}, "gesamt_m": meter}
    return beste


def _bester_treffpunkt(gruppe: List[int], weg: Weg, treffpunkte: Dict[int, List[int]]) -> Optional[Dict]:
    """
    Cheapest driver and meeting point for a group: the others drive there on
    their own and back again later. None if no candidate has all legs known.
    """
    beste = None
    for fahrer in gruppe:
        andere = [p for p in gruppe if p != fahrer]
        for punkt in treffpunkte.get(fahrer, []):
            teile = [weg(fahrer, punkt), weg(punkt, 0), weg(0, punkt), weg(punkt, fahrer)]
            fahrer_m = None if any(m is None for m in teile) else sum(teile)
            zubringer = {p: _hin_und_zurueck(weg, p, punkt) for p in andere}
            if fahrer_m is None or any(m is None for m in zubringer.values()):
                continue
            gesamt = fahrer_m + sum(zubringer.values())
            if beste is None or gesamt < beste["gesamt_m"]:
                beste = {"fahrer": fahrer, "mitfahrer": andere, "treffpunkt": punkt,
                         "meter": {fahrer: fahrer_m, **zubringer}, "gesamt_m": gesamt}
    return beste


def _variante(fahrten: List[Dict], personen: Sequence[str], einzeln_gesamt: int) -> Optional[Dict]:
    """Turns the cars of one split into a suggestion; None if it saves nothing."""
    km = {p: 0 for p in personen}
    beschrieben = []
    for fahrt in fahrten:
        for index, meter in fahrt["meter"].items():
            km[personen[index - 1]] = _km(meter)
        eintrag = {
            "fahrer": personen[fahrt["fahrer"] - 1],
            "mitfahrer": [personen[m - 1] for m in fahrt["mitfahrer"]],
            "km": _km(fahrt["meter"][fahrt["fahrer"]]),
            "treffpunkt": fahrt["treffpunkt"],
        }
        if fahrt["treffpunkt"] is not None:
            eintrag["zubringer"] = {personen[m - 1]: _km(fahrt["meter"][m]) for m in fahrt["mitfahrer"]}
        beschrieben.append(eintrag)

    gesamt = sum(km.values())
    if gesamt >= einzeln_gesamt:
        return None
    # People driving alone last, cars ordered by the driver's role
    beschrieben.sort(key=lambda f: (not f["mitfahrer"], personen.index(f["fahrer"])))
    return {"fahrten": beschrieben, "km": km, "gesamt": gesamt, "ersparnis": einzeln_gesamt - gesamt}


def planen(personen: Sequence[str], weg: Weg, treffpunkte: Optional[Dict[int, List[int]]] = None) -> Dict:
    """
    Works out the suggestions for persons given as form prefixes ("sr", "sra1").

    weg(i, j) returns the metres from point i to j; 0 is the venue, i >= 1 the
    home of personen[i - 1], higher indices are candidate meeting points.
    None means "unknown". treffpunkte maps a driver's index to the indices of
    their candidate meeting points.

    In the result, "treffpunkt" of a car is the index of its meeting point,
    or None for pick-ups. Returned are up to MAX_VORSCHLAEGE suggestions: the
    best pick-up variants plus the best meeting-point variant (see above).
    """
    treffpunkte = treffpunkte or {}
    indizes = list(range(1, len(personen) + 1))

    einzeln: Dict[str, int] = {}
    for i in indizes:
        meter = _hin_und_zurueck(weg, i, 0)
        if meter is not None:
            einzeln[personen[i - 1]] = _km(meter)
    einzeln_gesamt = sum(einzeln.values())

    abhol_varianten: List[Dict] = []
    treff_varianten: List[Dict] = []
    # Comparable with "everyone alone" only if every single trip is known
    if len(einzeln) == len(personen):
        for teilung in _teilungen(indizes):
            if all(len(gruppe) == 1 for gruppe in teilung):
                continue

            abholung, treffen = [], []
            for gruppe in teilung:
                if len(gruppe) == 1:
                    allein = {"fahrer": gruppe[0], "mitfahrer": [], "treffpunkt": None,
                              "meter": {gruppe[0]: _hin_und_zurueck(weg, gruppe[0], 0)}}
                    abholung.append(allein)
                    treffen.append(allein)
                else:
                    abholung.append(_beste_abholung(gruppe, weg))
                    treffen.append(_bester_treffpunkt(gruppe, weg, treffpunkte))

            for fahrten, ziel in ((abholung, abhol_varianten), (treffen, treff_varianten)):
                if any(f is None for f in fahrten):
                    continue
                variante = _variante(fahrten, personen, einzeln_gesamt)
                if variante and variante not in ziel:
                    ziel.append(variante)

    def sortiert(liste):
        return sorted(liste, key=lambda v: (v["gesamt"], len(v["fahrten"])))

    # A meeting point that splits the kilometres exactly like a pick-up (the
    # point lies at a passenger's door) adds nothing
    abhol_km = [v["km"] for v in abhol_varianten]
    treff_varianten = [v for v in sortiert(treff_varianten) if v["km"] not in abhol_km]
    abhol_varianten = sortiert(abhol_varianten)

    auswahl = abhol_varianten[:MAX_VORSCHLAEGE - 1] + treff_varianten[:1]
    rest = abhol_varianten[MAX_VORSCHLAEGE - 1:] + treff_varianten[1:]
    auswahl += sortiert(rest)[:MAX_VORSCHLAEGE - len(auswahl)]

    return {
        "einzeln": {"km": einzeln, "gesamt": einzeln_gesamt},
        "fahrgemeinschaften": sortiert(auswahl),
    }


def treffpunkt_kandidaten(von: Tuple[float, float], nach: Tuple[float, float]) -> List[Tuple[float, float]]:
    """
    Candidate meeting points between a home and the venue: evenly spread on
    the straight line, without the two end points. The route planner snaps
    each to the nearest road, so they need not lie on one.
    """
    km = luftlinie_m(von, nach) / 1000
    anzahl = max(1, min(MAX_TREFFPUNKTE_JE_FAHRER, math.floor(km / TREFFPUNKT_ABSTAND_KM)))
    return [runden((von[0] + (nach[0] - von[0]) * k / (anzahl + 1),
                    von[1] + (nach[1] - von[1]) * k / (anzahl + 1)))
            for k in range(1, anzahl + 1)]


def personen_mit_anschrift(match: Dict) -> List[Dict]:
    """The persons in the form roles with name and place, in form order."""
    gespann = match.get("schiedsrichter") or []
    personen = []
    for rolle, seq, praefix in FORM_ROLES:
        treffer = [p for p in gespann if p.get("rolle") == rolle]
        if len(treffer) <= seq or not treffer[seq].get("name"):
            continue
        person = treffer[seq]
        personen.append({"praefix": praefix, "rolle": rolle, "name": person["name"],
                         "strasse": (person.get("strasse") or "").strip(),
                         "plz_ort": (person.get("plz_ort") or "").strip()})
    return personen


def spielort_aus(match: Dict, suche) -> Optional[Tuple[float, float]]:
    """
    Coordinate of the venue: from DFBnet, otherwise via its address.
    suche(address) returns a point or None - geocode directly or with a time budget.
    """
    if match.get("staette_lat") is not None and match.get("staette_lon") is not None:
        return match["staette_lat"], match["staette_lon"]
    adresse = ((match.get("spielstaette") or {}).get("adresse") or "").strip()
    return suche(adresse) if adresse else None


def spielort(match: Dict) -> Optional[Tuple[float, float]]:
    def suche(adresse):
        treffer = geocode(adresse)
        return (treffer["lat"], treffer["lon"]) if treffer else None
    return spielort_aus(match, suche)


def _wegtabelle(punkte: List[Tuple[float, float]], kandidaten: List[Tuple[float, float]]) -> Tuple[Weg, str]:
    """
    Distances between venue/homes and to/from the candidate meeting points.
    Falls back to the straight line times UMWEGFAKTOR if the route planner
    does not answer; the second value says which ("strasse"/"luftlinie").
    """
    try:
        basis = entfernungen(punkte, punkte).meter
        zu = entfernungen(punkte, kandidaten).meter if kandidaten else []
        von = entfernungen(kandidaten, punkte).meter if kandidaten else []
        quelle = "strasse"
    except RoutingNichtErreichbar:
        def schaetzung(a, b):
            return luftlinie_m(a, b) * UMWEGFAKTOR
        basis = [[schaetzung(a, b) for b in punkte] for a in punkte]
        zu = [[schaetzung(a, k) for k in kandidaten] for a in punkte]
        von = [[schaetzung(k, b) for b in punkte] for k in kandidaten]
        quelle = "luftlinie"

    n = len(punkte)

    def weg(i: int, j: int) -> Optional[float]:
        if i < n and j < n:
            return basis[i][j]
        if i < n:
            return zu[i][j - n]
        if j < n:
            return von[i - n][j]
        return None

    return weg, quelle


def vorschlaege_fuer_spiel(match: Dict) -> Dict:
    """
    Mileage suggestions for a match from the database.

    Persons without an address that can be found are left out and named.
    If the route planner does not answer, the straight line times
    UMWEGFAKTOR is used - "quelle" says so ("strasse", "luftlinie", or
    "gestoert" if already the address lookup failed).
    """
    selbst = match.get("selbst") or {}
    eigene = next((p for r, s, p in FORM_ROLES if r == selbst.get("rolle") and s == selbst.get("seq")), None)
    antwort = {"quelle": "strasse", "selbst": eigene, "einzeln": {"km": {}, "gesamt": 0},
               "fahrgemeinschaften": [], "ohne_anschrift": [], "ohne_spielort": False}

    try:
        ort = spielort(match)
        if ort is None:
            antwort["ohne_spielort"] = True
            return antwort

        personen, punkte = [], [ort]
        for person in personen_mit_anschrift(match):
            treffer = None
            if person["plz_ort"]:
                adresse = f"{person['strasse']}, {person['plz_ort']}" if person["strasse"] else person["plz_ort"]
                treffer = geocode(adresse, person["plz_ort"])
            if not treffer:
                antwort["ohne_anschrift"].append(person["rolle"])
                continue
            personen.append(person["praefix"])
            punkte.append((treffer["lat"], treffer["lon"]))
    except GeocoderNichtErreichbar:
        # Without the address lookup points are missing - better no suggestion than half values
        antwort["quelle"] = "gestoert"
        return antwort

    if not personen:
        return antwort

    # Meeting points only make sense with at least two people
    kandidaten: List[Tuple[float, float]] = []
    treffpunkte: Dict[int, List[int]] = {}
    if len(personen) >= 2:
        for i in range(1, len(punkte)):
            for kandidat in treffpunkt_kandidaten(punkte[i], ort):
                if kandidat not in kandidaten:
                    kandidaten.append(kandidat)
                treffpunkte.setdefault(i, []).append(len(punkte) + kandidaten.index(kandidat))

    weg, antwort["quelle"] = _wegtabelle(punkte, kandidaten)
    antwort.update(planen(personen, weg, treffpunkte))

    # Meeting point indices -> coordinate and the name of the nearest place
    for vorschlag in antwort["fahrgemeinschaften"]:
        for fahrt in vorschlag["fahrten"]:
            if fahrt["treffpunkt"] is not None:
                lat, lon = kandidaten[fahrt["treffpunkt"] - len(punkte)]
                fahrt["treffpunkt"] = {"lat": lat, "lon": lon, "name": ortsname(lat, lon)}
    return antwort
