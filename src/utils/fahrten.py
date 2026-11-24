"""
Kilometer-Vorschlaege fuer die Fahrtkosten eines Gespanns.

Zwei Arten zu fahren werden durchgerechnet:

- Jede Person faehrt allein: Wohnort -> Spielort -> Wohnort.
- Fahrgemeinschaften: eine Person faehrt und sammelt andere auf dem Weg ein,
  auf der Rueckfahrt in umgekehrter Reihenfolge wieder ab. Abgerechnet wird
  die ganze Strecke beim Fahrer, Mitfahrer tragen 0 km ein.

Gerechnet wird jede Aufteilung des Gespanns in Autos, je Auto mit dem
guenstigsten Fahrer und der guenstigsten Abholreihenfolge. Vorgeschlagen
werden die Aufteilungen, die gegenueber "jeder allein" Kilometer sparen.

Alle Werte sind Hin- und Rueckfahrt zusammen, auf ganze Kilometer gerundet -
so steht es auch im Abrechnungsformular.
"""
from itertools import permutations
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from db.matches import FORM_ROLES
from utils.geocoder import GeocoderNichtErreichbar, geocode
from utils.logger import setup_logger
from utils.routing import UMWEGFAKTOR, RoutingNichtErreichbar, entfernungen, luftlinie_m

logger = setup_logger("fahrten")

# Index 0 ist der Spielort, 1..n die Wohnorte in der Reihenfolge der Personen
Weg = Callable[[int, int], Optional[float]]

MAX_VORSCHLAEGE = 3


def _km(meter: float) -> int:
    """Ganze Kilometer, kaufmaennisch gerundet (round() rundet 0,5 zur geraden Zahl)."""
    return int(meter / 1000 + 0.5)


def _teilungen(elemente: List[int]) -> List[List[List[int]]]:
    """Alle Aufteilungen einer Menge in nichtleere Gruppen (Bell-Zahl; hier hoechstens drei Personen)."""
    if not elemente:
        return [[]]
    erstes, rest = elemente[0], elemente[1:]
    ergebnis = []
    for teilung in _teilungen(rest):
        ergebnis.append([[erstes]] + teilung)
        for i in range(len(teilung)):
            ergebnis.append(teilung[:i] + [[erstes] + teilung[i]] + teilung[i + 1:])
    return ergebnis


def _beste_fahrt(gruppe: List[int], weg: Weg) -> Optional[Tuple[float, int, List[int]]]:
    """
    Guenstigster Fahrer samt Abholreihenfolge fuer eine Gruppe.
    Rueckgabe (Meter hin und zurueck, Fahrer, Mitfahrer in Abholreihenfolge),
    None, wenn ein noetiges Teilstueck unbekannt ist.
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
            if beste is None or meter < beste[0]:
                beste = (meter, fahrer, list(reihenfolge))
    return beste


def planen(personen: Sequence[str], weg: Weg) -> Dict:
    """
    Rechnet die Vorschlaege fuer Personen (Formular-Praefixe wie "sr", "sra1").

    weg(i, j) liefert die Meter von Punkt i nach j; 0 ist der Spielort, i >= 1
    der Wohnort von personen[i - 1]. None heisst "unbekannt".
    """
    indizes = list(range(1, len(personen) + 1))

    einzeln: Dict[str, int] = {}
    for i in indizes:
        hin, zurueck = weg(i, 0), weg(0, i)
        if hin is not None and zurueck is not None:
            einzeln[personen[i - 1]] = _km(hin + zurueck)
    einzeln_gesamt = sum(einzeln.values())

    fahrgemeinschaften = []
    # Vergleichbar mit "jeder allein" ist eine Aufteilung nur, wenn fuer alle
    # die Einzelfahrt bekannt ist
    if len(einzeln) == len(personen):
        for teilung in _teilungen(indizes):
            if all(len(gruppe) == 1 for gruppe in teilung):
                continue
            km = {p: 0 for p in personen}
            fahrten = []
            for gruppe in teilung:
                beste = _beste_fahrt(gruppe, weg)
                if beste is None:
                    break
                meter, fahrer, mitfahrer = beste
                km[personen[fahrer - 1]] = _km(meter)
                fahrten.append({
                    "fahrer": personen[fahrer - 1],
                    "mitfahrer": [personen[m - 1] for m in mitfahrer],
                    "km": _km(meter),
                })
            else:
                gesamt = sum(km.values())
                if gesamt < einzeln_gesamt:
                    # Allein fahrende Personen zuletzt, Autos nach Fahrerrolle
                    fahrten.sort(key=lambda f: (not f["mitfahrer"], personen.index(f["fahrer"])))
                    fahrgemeinschaften.append({
                        "fahrten": fahrten,
                        "km": km,
                        "gesamt": gesamt,
                        "ersparnis": einzeln_gesamt - gesamt,
                    })

    fahrgemeinschaften.sort(key=lambda v: (v["gesamt"], len(v["fahrten"])))
    return {
        "einzeln": {"km": einzeln, "gesamt": einzeln_gesamt},
        "fahrgemeinschaften": fahrgemeinschaften[:MAX_VORSCHLAEGE],
    }


def _personen_mit_anschrift(match: Dict) -> List[Dict]:
    """Die Personen der Formularrollen mit Name und Ort, in Formularreihenfolge."""
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
    Koordinate des Spielorts: aus DFBnet, sonst ueber die Adresse. suche(adresse)
    liefert einen Punkt oder None - geocode direkt oder mit Zeitbudget.
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


def vorschlaege_fuer_spiel(match: Dict) -> Dict:
    """
    Kilometer-Vorschlaege fuer ein Spiel aus der Datenbank.

    Personen ohne auffindbare Anschrift bleiben aussen vor und werden
    genannt. Antwortet der Routenplaner nicht, wird mit der Luftlinie mal
    UMWEGFAKTOR gerechnet - die Antwort sagt das in "quelle" ("strasse",
    "luftlinie", oder "gestoert", wenn schon die Adresssuche ausfiel).
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
        for person in _personen_mit_anschrift(match):
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
        # Ohne Adresssuche fehlen Punkte - lieber nichts vorschlagen als halbe Werte
        antwort["quelle"] = "gestoert"
        return antwort

    if not personen:
        return antwort

    try:
        meter = entfernungen(punkte, punkte).meter
    except RoutingNichtErreichbar:
        antwort["quelle"] = "luftlinie"
        meter = [[luftlinie_m(a, b) * UMWEGFAKTOR for b in punkte] for a in punkte]

    antwort.update(planen(personen, lambda i, j: meter[i][j]))
    return antwort
