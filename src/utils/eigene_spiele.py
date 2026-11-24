"""
Building blocks for analyses of the user's own matches: which role one held
in the crew, and coordinates for addresses with a time budget.

The analyses (statistics, map of venues) run over dozens of
matches. The address search and the route planner are public services with one
request per second - a first call must therefore not ask for everything at once. It takes
what is in the cache, queries until a deadline,
and reports the rest as "offen" (open); the frontend then calls again.
"""
import re
import time
from typing import Dict, Optional, Tuple

from utils.geocoder import GeocoderNichtErreichbar, geocode, geocode_bekannt

Punkt = Tuple[float, float]

# For this long a call may start new requests
STANDARD_FRIST_SEKUNDEN = 8.0


def _namensteile(name: str) -> frozenset:
    return frozenset(w for w in re.split(r"[\W_]+", (name or "").casefold()) if w)


def eigene_person(match: Dict, name_vorname: str = "") -> Optional[Dict]:
    """
    The user's own person in the crew of a match: {"rolle", "seq", ...person fields}.

    First via the marker from the assignment (match["selbst"]), for
    matches from before that via the name from the master data (Stammdaten) ("Muster,
    Max" is "Max Muster"). If the name fits more than one person, it stays
    open - better no role than a wrong one.
    """
    gespann = match.get("schiedsrichter") or []
    mit_seq = []
    zaehler: Dict[str, int] = {}
    for person in gespann:
        rolle = person.get("rolle") or ""
        seq = zaehler.get(rolle, 0)
        zaehler[rolle] = seq + 1
        mit_seq.append({**person, "rolle": rolle, "seq": seq})

    selbst = match.get("selbst")
    if selbst:
        for person in mit_seq:
            if person["rolle"] == selbst.get("rolle") and person["seq"] == selbst.get("seq"):
                return person

    teile = _namensteile(name_vorname)
    if not teile:
        return None
    treffer = [p for p in mit_seq if _namensteile(p.get("name") or "") == teile]
    return treffer[0] if len(treffer) == 1 else None


def wohnadresse(person: Dict) -> Tuple[str, str]:
    """(Address, town) of a person for the address search; empty without a town."""
    strasse = (person.get("strasse") or "").strip()
    plz_ort = (person.get("plz_ort") or "").strip()
    if not plz_ort:
        return "", ""
    return (f"{strasse}, {plz_ort}" if strasse else plz_ort), plz_ort


class Ortsuche:
    """Addresses -> coordinates, new requests only until the deadline."""

    def __init__(self, frist: Optional[float] = None):
        self.frist = frist if frist is not None else time.monotonic() + STANDARD_FRIST_SEKUNDEN
        self.offen = 0
        self.gestoert = False
        self._bekannt: Dict[Tuple[str, Optional[str]], Optional[Dict]] = {}

    def treffer(self, adresse: str, ort: Optional[str] = None) -> Optional[Dict]:
        """{"lat", "lon", "genauigkeit"} or None - unknown or not (yet) queried."""
        schluessel = (adresse, ort)
        if not adresse or not adresse.strip():
            return None
        if schluessel in self._bekannt:
            return self._bekannt[schluessel]

        gefunden, offen = geocode_bekannt(adresse, ort)
        if offen:
            if self.gestoert or time.monotonic() >= self.frist:
                self.offen += 1
                gefunden = None
            else:
                try:
                    gefunden = geocode(adresse, ort)
                except GeocoderNichtErreichbar:
                    self.gestoert = True
                    self.offen += 1
                    gefunden = None

        self._bekannt[schluessel] = gefunden
        return gefunden

    def punkt(self, adresse: str, ort: Optional[str] = None) -> Optional[Punkt]:
        gefunden = self.treffer(adresse, ort)
        return (gefunden["lat"], gefunden["lon"]) if gefunden else None
