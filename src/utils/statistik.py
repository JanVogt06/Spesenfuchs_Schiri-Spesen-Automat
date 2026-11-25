"""
Own expenses and travel costs per season.

Which matches count: the ones DFBnet lists as officiated ("Spiele &
Statistik", stored in season_matches) - the same list and number as in the
"Saison" tab. Appointments alone are not proof: an appointment can be given
back or re-staffed before the match, and before the first fetch of an
account there are none at all. For a season without that list (not read
yet) the past appointments that were not withdrawn are counted instead.

For each officiated match the stored appointment is looked up (same day,
one of the teams). From it come the frozen expense rate of the own role,
entered kilometres and public transport, and the venue. Without an
appointment the rate is computed from the league DFBnet names for the
match, and the venue comes from the match report.

Travel costs where nothing was entered for the own role are estimated the
way the mileage suggestions on a match card work (utils.fahrten): with the
whole crew of the appointment, taking the suggestion with the fewest total
kilometres - a carpool where one saves kilometres, otherwise everyone alone.
The own kilometres are those of that suggestion: as driver the whole trip
with pick-ups, as passenger 0. Without an appointment (no crew known) the
estimate is the trip alone from the own home. The answer keeps entered and
estimated amounts apart.
"""
import re
import time
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Tuple

from db.matches import FORM_ROLES, get_matches_for_user
from db.season import get_eigene_rollen
from db.spielberichte import get_spielorte, gleiches_team
from db.stammdaten import get_stammdaten
from generator.spesen_calculator import calculate_spesen
from utils.eigene_spiele import STANDARD_FRIST_SEKUNDEN, Ortsuche, eigene_person, wohnadresse
from utils.fahrten import personen_mit_anschrift, planen, spielort_aus
from utils.routing import UMWEGFAKTOR, RoutingNichtErreichbar, entfernungen, luftlinie_m
from utils.saison_utils import saison_fuer_datum

STANDARD_KM_SATZ = 0.30

# Team types DFBnet puts in front of the league in the list of officiated
# matches ("B-Junioren Bundesliga", "Herren Ü40 Landespokal")
_MANNSCHAFTSART = re.compile(
    r"^((?:[A-G]-Junior(?:en|innen))|Juniorinnen|Frauen|Alte Herren|Altsenioren|Senioren|Herren(?: Ü\d+)?)\s+(.+)$"
)
# Abbreviations of that list -> the league names of the appointments
_KUERZEL = {"TFV-Pokal": "Thüringen-Pokal"}


def klasse_und_art(liga: str) -> Tuple[str, str]:
    """
    Splits the league of an officiated match into (Spielklasse, Mannschaftsart)
    as the appointments name them: "Kreis-FS" -> ("Kreisfreundschaftsspiele",
    "Herren"), "B-Junioren Bundesliga" -> ("Bundesliga", "B-Junioren").
    """
    liga = (liga or "").strip()
    treffer = _MANNSCHAFTSART.match(liga)
    art, klasse = (treffer.group(1), treffer.group(2)) if treffer else ("Herren", liga)
    klasse = _KUERZEL.get(klasse, klasse)
    fs = re.fullmatch(r"(\w+)-FS", klasse)
    if fs:
        klasse = f"{fs.group(1)}freundschaftsspiele"
    return klasse, art


def _praefix(rolle: str, seq: int) -> Optional[str]:
    return next((p for r, s, p in FORM_ROLES if r == rolle and s == seq), None)


def _gueltiges_datum(datum: Optional[str]) -> bool:
    return bool(datum) and datum != "1900-01-01"


def _euro(wert: float) -> float:
    return round(wert + 1e-9, 2)


def _zur_ansetzung(spiel: Dict, ansetzungen: List[Dict]) -> Optional[Dict]:
    """
    The stored appointment of an officiated match: same day, one of the teams.
    Tournaments have no teams in the appointment (DFBnet's list names the
    tournament block instead) - there the one tournament of the day counts.
    """
    am_tag = [m for m in ansetzungen if m.get("datum") == spiel["datum"]]
    beide = [m for m in am_tag if gleiches_team(m.get("heim_team"), spiel["heim"])
             and gleiches_team(m.get("gast_team"), spiel["gast"])]
    eine = beide or [m for m in am_tag if gleiches_team(m.get("heim_team"), spiel["heim"])
                     or gleiches_team(m.get("gast_team"), spiel["gast"])]
    if not eine:
        turniere = [m for m in am_tag if not m.get("heim_team") and not m.get("gast_team")]
        eine = turniere if len(turniere) == 1 else []
    # Prefer one that is still assigned - a re-staffed appointment of the same day is not it
    eine.sort(key=lambda m: m.get("missing_since") is not None)
    return eine[0] if eine else None


def _zum_bericht(spiel: Dict, berichte: List[Dict]) -> Optional[Dict]:
    for bericht in berichte:
        if bericht.get("datum") == spiel["datum"] and (
                gleiches_team(bericht.get("heim"), spiel["heim"]) or gleiches_team(bericht.get("gast"), spiel["gast"])):
            return bericht
    return None


def _einsaetze_aus_dfbnet(geleitete: List[Dict], ansetzungen: List[Dict], user_id: int,
                          stammdaten: Dict) -> List[Dict]:
    """One entry per officiated match, completed from appointment or report."""
    berichte = None
    heim_der_stammdaten = wohnadresse({"strasse": stammdaten.get("strasse"), "plz_ort": stammdaten.get("plz_ort")})
    einsaetze = []
    for spiel in geleitete:
        rolle = (spiel.get("eigene_rolle") or "").strip()
        match = _zur_ansetzung(spiel, ansetzungen)
        eintrag = {"datum": spiel["datum"], "rolle": rolle, "ansetzung": match is not None}

        if match:
            person = eigene_person(match, stammdaten.get("name_vorname") or "")
            if person is None or person["rolle"] != rolle:
                treffer = [p for p in match.get("schiedsrichter") or [] if p.get("rolle") == rolle]
                person = {**treffer[0], "rolle": rolle, "seq": 0} if len(treffer) == 1 else None
            eintrag["satz"] = match.get("sr_spesen") if rolle == "SR" else match.get("sra_spesen")
            eintrag["km_satz"] = match.get("km_satz") or STANDARD_KM_SATZ
            praefix = _praefix(rolle, person["seq"] if person else 0)
            kosten = match.get("expenses") or {}
            eintrag["km"] = kosten.get(f"{praefix}_km") if praefix else None
            eintrag["oevm"] = kosten.get(f"{praefix}_oevm") if praefix else None
            eintrag["wohnort"] = wohnadresse(person) if person else heim_der_stammdaten
            eintrag["platz"] = ("ansetzung", match)
            eintrag["eigen"] = praefix
            eintrag["gespann"] = personen_mit_anschrift(match)
        else:
            klasse, art = klasse_und_art(spiel.get("liga") or "")
            sr, sra = calculate_spesen(klasse, art, "", spiel.get("heim") or "", spiel.get("gast") or "")
            eintrag["satz"] = sr if rolle == "SR" else sra
            eintrag["km_satz"] = STANDARD_KM_SATZ
            eintrag["km"] = eintrag["oevm"] = None
            eintrag["wohnort"] = heim_der_stammdaten
            eintrag["eigen"] = None
            eintrag["gespann"] = []
            if berichte is None:
                berichte = [b for b in get_spielorte(user_id) if not b["ausgefallen"]]
            bericht = _zum_bericht(spiel, berichte)
            staette = (bericht or {}).get("spielstaette") or {}
            adresse = ", ".join(t for t in (staette.get("strasse"), staette.get("ort")) if t)
            eintrag["platz"] = ("adresse", adresse) if adresse else None

        if rolle not in ("SR", "SRA 1", "SRA 2"):
            # Fourth official, observer and the like: no rate in the regulations
            eintrag["satz"] = None
        einsaetze.append(eintrag)
    return einsaetze


def _einsaetze_aus_ansetzungen(ansetzungen: List[Dict], stammdaten: Dict) -> Tuple[List[Dict], int]:
    """Fallback without DFBnet's list: past appointments that were not withdrawn."""
    einsaetze, ohne_rolle = [], 0
    for match in ansetzungen:
        if match.get("missing_since"):
            continue
        person = eigene_person(match, stammdaten.get("name_vorname") or "")
        if person is None:
            ohne_rolle += 1
            continue
        praefix = _praefix(person["rolle"], person["seq"])
        kosten = match.get("expenses") or {}
        einsaetze.append({
            "datum": match["datum"],
            "rolle": person["rolle"],
            "ansetzung": True,
            "satz": match.get("sr_spesen") if person["rolle"] == "SR" else match.get("sra_spesen"),
            "km_satz": match.get("km_satz") or STANDARD_KM_SATZ,
            "km": kosten.get(f"{praefix}_km") if praefix else None,
            "oevm": kosten.get(f"{praefix}_oevm") if praefix else None,
            "wohnort": wohnadresse(person),
            "platz": ("ansetzung", match),
            "eigen": praefix,
            "gespann": personen_mit_anschrift(match),
        })
    return einsaetze, ohne_rolle


def statistik(user_id: int, saison: Optional[str] = None, frist: Optional[float] = None,
              heute: Optional[date] = None) -> Dict:
    heute_iso = (heute or date.today()).isoformat()
    frist = frist if frist is not None else time.monotonic() + STANDARD_FRIST_SEKUNDEN

    ansetzungen = [m for m in get_matches_for_user(user_id)
                   if _gueltiges_datum(m.get("datum")) and m["datum"] < heute_iso]
    for match in ansetzungen:
        match["_saison"] = saison_fuer_datum(date.fromisoformat(match["datum"]))

    geleitete = [g for g in get_eigene_rollen(user_id) if _gueltiges_datum(g.get("datum"))]
    saisons_dfbnet = {g["saison"] for g in geleitete}
    saisons = sorted(saisons_dfbnet | {m["_saison"] for m in ansetzungen if not m.get("missing_since")},
                     reverse=True)
    if saison not in saisons:
        saison = saisons[0] if saisons else None

    stammdaten = get_stammdaten(user_id) or {}
    if saison in saisons_dfbnet:
        quelle = "dfbnet"
        einsaetze = _einsaetze_aus_dfbnet([g for g in geleitete if g["saison"] == saison],
                                          ansetzungen, user_id, stammdaten)
        ohne_rolle = 0
    else:
        quelle = "ansetzungen"
        einsaetze, ohne_rolle = _einsaetze_aus_ansetzungen(
            [m for m in ansetzungen if m["_saison"] == saison], stammdaten)

    ortsuche = Ortsuche(frist)
    monate: Dict[str, Dict] = defaultdict(lambda: {"spiele": 0, "spesen": 0.0,
                                                   "fahrt_erfasst": 0.0, "fahrt_geschaetzt": 0.0})
    rollen: Dict[str, Dict] = defaultdict(lambda: {"spiele": 0, "spesen": 0.0})
    summe = {"spiele": 0, "ohne_satz": 0, "ohne_ansetzung": 0, "spesen": 0.0}
    fahrt = {"erfasst": 0.0, "erfasst_spiele": 0, "geschaetzt": 0.0, "geschaetzt_spiele": 0,
             "geschaetzt_km": 0, "ohne_schaetzung": 0, "luftlinie_spiele": 0,
             # Of the estimated: how many follow a carpool, and in how many you ride along
             "fahrgemeinschaft_spiele": 0, "mitfahrer_spiele": 0}
    zu_schaetzen = []

    for einsatz in einsaetze:
        monat = monate[einsatz["datum"][:7]]
        summe["spiele"] += 1
        monat["spiele"] += 1
        rollen[einsatz["rolle"] or "?"]["spiele"] += 1
        summe["ohne_ansetzung"] += 0 if einsatz["ansetzung"] else 1

        if einsatz["satz"] is None:
            summe["ohne_satz"] += 1
        else:
            summe["spesen"] += einsatz["satz"]
            monat["spesen"] += einsatz["satz"]
            rollen[einsatz["rolle"]]["spesen"] += einsatz["satz"]

        if einsatz["km"] is not None or einsatz["oevm"] is not None:
            betrag = (einsatz["km"] or 0) * einsatz["km_satz"] + (einsatz["oevm"] or 0)
            fahrt["erfasst"] += betrag
            fahrt["erfasst_spiele"] += 1
            monat["fahrt_erfasst"] += betrag
            continue

        adresse, ort = einsatz["wohnort"]
        wohnort = ortsuche.punkt(adresse, ort) if adresse else None
        platz = None
        if einsatz["platz"] and einsatz["platz"][0] == "ansetzung":
            platz = spielort_aus(einsatz["platz"][1], ortsuche.punkt)
        elif einsatz["platz"]:
            platz = ortsuche.punkt(einsatz["platz"][1])
        if wohnort is None or platz is None:
            fahrt["ohne_schaetzung"] += 1
            continue

        # The others of the crew whose home can be found; anyone else simply
        # does not take part in the carpool, like on the match card
        kollegen = []
        for person in einsatz["gespann"]:
            if person["praefix"] == einsatz["eigen"] or not person["plz_ort"]:
                continue
            adresse_k = f"{person['strasse']}, {person['plz_ort']}" if person["strasse"] else person["plz_ort"]
            punkt = ortsuche.punkt(adresse_k, person["plz_ort"])
            if punkt:
                kollegen.append((person["praefix"], punkt))

        zu_schaetzen.append({"monat": einsatz["datum"][:7], "km_satz": einsatz["km_satz"], "platz": platz,
                             "wohnort": wohnort, "eigen": einsatz["eigen"] if kollegen else None,
                             "kollegen": kollegen if einsatz["eigen"] else []})

    offen_strecken = _schaetzen(zu_schaetzen, frist, monate, fahrt)

    for monat in monate.values():
        for feld in ("spesen", "fahrt_erfasst", "fahrt_geschaetzt"):
            monat[feld] = _euro(monat[feld])

    fahrt["erfasst"] = _euro(fahrt["erfasst"])
    fahrt["geschaetzt"] = _euro(fahrt["geschaetzt"])
    return {
        "saisons": saisons,
        "saison": saison,
        # dfbnet: the officiated matches DFBnet lists; ansetzungen: fallback without that list
        "quelle": quelle,
        "spiele": summe["spiele"],
        "ohne_rolle": ohne_rolle,
        "ohne_satz": summe["ohne_satz"],
        # Officiated, but no appointment stored: rate computed from the league
        "ohne_ansetzung": summe["ohne_ansetzung"],
        "spesen": _euro(summe["spesen"]),
        "fahrtkosten": fahrt,
        "gesamt": _euro(summe["spesen"] + fahrt["erfasst"] + fahrt["geschaetzt"]),
        "monate": [{"monat": k, **v} for k, v in sorted(monate.items())],
        "rollen": [{"rolle": k, "spiele": v["spiele"], "spesen": _euro(v["spesen"])}
                   for k, v in sorted(rollen.items())],
        # Not looked up yet: the frontend asks again
        "offen": ortsuche.offen + offen_strecken,
    }


def _schaetzen(zu_schaetzen: List[Dict], frist: float, monate, fahrt) -> int:
    """
    Adds the estimated travel costs; returns the number of matches still open.

    All points of all matches go into one distance table - homes of the
    colleagues and venues repeat over a season, so this is a handful of
    requests to the route planner instead of one per match.
    """
    punkte = list(dict.fromkeys(
        p for e in zu_schaetzen for p in (e["platz"], e["wohnort"], *(k[1] for k in e["kollegen"]))))
    if not punkte:
        return 0

    luftlinie = False
    try:
        meter = entfernungen(punkte, punkte, frist).meter
    except RoutingNichtErreichbar:
        luftlinie = True
        meter = [[luftlinie_m(a, b) * UMWEGFAKTOR for b in punkte] for a in punkte]
    index = {p: i for i, p in enumerate(punkte)}

    offen = 0
    for e in zu_schaetzen:
        # Planner indices: 0 venue, 1 own home, then the colleagues
        lokal = [e["platz"], e["wohnort"], *(k[1] for k in e["kollegen"])]

        def weg(i: int, j: int, lokal=lokal) -> Optional[float]:
            return meter[index[lokal[i]]][index[lokal[j]]]

        eigen = e["eigen"] or "selbst"
        personen = [eigen, *(k[0] for k in e["kollegen"])]
        plan = planen(personen, weg)
        vorschlag = plan["fahrgemeinschaften"][0] if plan["fahrgemeinschaften"] else None
        km = vorschlag["km"][eigen] if vorschlag else plan["einzeln"]["km"].get(eigen)
        if km is None:
            offen += 1
            continue

        if vorschlag:
            fahrt["fahrgemeinschaft_spiele"] += 1
            fahrt["mitfahrer_spiele"] += 1 if km == 0 else 0
        betrag = km * e["km_satz"]
        fahrt["geschaetzt"] += betrag
        fahrt["geschaetzt_spiele"] += 1
        fahrt["geschaetzt_km"] += km
        fahrt["luftlinie_spiele"] += 1 if luftlinie else 0
        monate[e["monat"]]["fahrt_geschaetzt"] += betrag

    return offen
