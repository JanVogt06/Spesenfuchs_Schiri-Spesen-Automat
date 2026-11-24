"""
Bausteine fuer Auswertungen ueber die eigenen Spiele: wer man im Gespann
war, und Koordinaten zu Adressen mit einem Zeitbudget.

Die Auswertungen (Statistik, Karte der Spielstaetten) laufen ueber Dutzende
Spiele. Adresssuche und Routenplaner sind oeffentliche Dienste mit einer
Anfrage je Sekunde - ein erster Aufruf darf deshalb nicht alles auf einmal
fragen. Er nimmt, was im Zwischenspeicher liegt, fragt bis zu einer Frist
nach und meldet den Rest als "offen"; das Frontend ruft dann noch einmal.
"""
import re
import time
from typing import Dict, Optional, Tuple

from utils.geocoder import GeocoderNichtErreichbar, geocode, geocode_bekannt

Punkt = Tuple[float, float]

# So lange darf ein Aufruf neue Anfragen beginnen
STANDARD_FRIST_SEKUNDEN = 8.0


def _namensteile(name: str) -> frozenset:
    return frozenset(w for w in re.split(r"[\W_]+", (name or "").casefold()) if w)


def eigene_person(match: Dict, name_vorname: str = "") -> Optional[Dict]:
    """
    Die eigene Person im Gespann eines Spiels: {"rolle", "seq", ...Personenfelder}.

    Erst ueber die Markierung aus der Ansetzung (match["selbst"]), fuer
    Spiele aus der Zeit davor ueber den Namen aus den Stammdaten ("Muster,
    Max" ist "Max Muster"). Passt der Name auf mehr als eine Person, bleibt
    es offen - lieber keine Rolle als eine falsche.
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
    """(Adresse, Ort) einer Person fuer die Adresssuche; leer ohne Ort."""
    strasse = (person.get("strasse") or "").strip()
    plz_ort = (person.get("plz_ort") or "").strip()
    if not plz_ort:
        return "", ""
    return (f"{strasse}, {plz_ort}" if strasse else plz_ort), plz_ort


class Ortsuche:
    """Adressen -> Koordinaten, neue Anfragen nur bis zur Frist."""

    def __init__(self, frist: Optional[float] = None):
        self.frist = frist if frist is not None else time.monotonic() + STANDARD_FRIST_SEKUNDEN
        self.offen = 0
        self.gestoert = False
        self._bekannt: Dict[Tuple[str, Optional[str]], Optional[Dict]] = {}

    def treffer(self, adresse: str, ort: Optional[str] = None) -> Optional[Dict]:
        """{"lat", "lon", "genauigkeit"} oder None - unbekannt oder (noch) nicht gefragt."""
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
