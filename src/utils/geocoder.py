"""
Adresse -> Koordinate, ueber Nominatim.

Gefragt wird nur, was nicht schon in der Datenbank steht (db.geocode). Das
ist keine Optimierung, sondern die Betriebsgrundlage: der oeffentliche
Nominatim-Dienst erlaubt eine Anfrage pro Sekunde aus einem einzelnen Thread
und verbietet Massenabfragen. Mit dem Zwischenspeicher bleibt es bei
geschaetzt hundert Anfragen ueber die Lebensdauer eines Kontos - die eigene
Anschrift ist eine einzige, Kollegen und Spielstaetten wiederholen sich.

NOMINATIM_URL zeigt auf einen eigenen Dienst, wenn gewuenscht; die
Voreinstellung ist der oeffentliche. Ein eigener Dienst darf schneller
gefragt werden, dafuer gibt es GEOCODER_MIN_INTERVAL.

Bewusst mit urllib statt requests/httpx: eine einzige GET-Anfrage rechtfertigt
keine zusaetzliche Abhaengigkeit.
"""
import json
import os
import re
import threading
import time
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.config import APP_VERSION
from db.geocode import get_cached, store
from utils.logger import setup_logger

logger = setup_logger("geocoder")

STANDARD_URL = "https://nominatim.openstreetmap.org"

# Nach dieser Zeit wird eine erfolglose Adresse noch einmal versucht. OSM
# waechst; was heute niemand kennt, kann in vier Wochen eingetragen sein.
MISS_GUELTIG_TAGE = 30

# Nominatim verlangt einen sprechenden User-Agent mit Kontaktmoeglichkeit.
# Ohne den antwortet der oeffentliche Dienst mit 403.
USER_AGENT = f"Spesenfuchs/{APP_VERSION} (+https://github.com/JanVogt06/dfb-spesen-generator)"

TIMEOUT_SEKUNDEN = 10

# Serialisiert alle Anfragen dieses Prozesses. Die Karte loest bis zu vier
# Adressen auf einmal auf, und mehrere Karten koennen gleichzeitig offen
# sein - ohne Schloss waeren das parallele Anfragen an einen Dienst, der
# ausdruecklich einen einzelnen Thread verlangt.
_schloss = threading.Lock()
_letzte_anfrage = 0.0


class GeocoderNichtErreichbar(Exception):
    """Der Dienst hat nicht geantwortet - anders als "Adresse unbekannt"."""


def basis_url() -> str:
    """Der konfigurierte Dienst, ohne abschliessenden Schraegstrich."""
    return (os.getenv("NOMINATIM_URL") or STANDARD_URL).rstrip("/")


def _min_intervall() -> float:
    """Mindestabstand zwischen zwei Anfragen an denselben Dienst."""
    try:
        return max(0.0, float(os.getenv("GEOCODER_MIN_INTERVAL", "1.0")))
    except ValueError:
        return 1.0


def _normalisieren(adresse: str) -> str:
    """Vereinheitlicht den Schluessel, unter dem eine Adresse zwischenliegt."""
    return re.sub(r"\s+", " ", adresse).strip(" ,").lower()


def _abfragen(adresse: str) -> Optional[Tuple[float, float]]:
    """
    Eine Anfrage an den Geocoder, unter Einhaltung des Mindestabstands.

    Gibt None zurueck, wenn der Dienst die Adresse nicht kennt. Antwortet er
    gar nicht, fliegt GeocoderNichtErreichbar - das darf nicht als "Adresse
    unbekannt" im Zwischenspeicher landen.
    """
    global _letzte_anfrage

    parameter = urlencode({
        "q": adresse,
        "format": "jsonv2",
        "limit": "1",
        "countrycodes": "de",
        "addressdetails": "1",
    })
    url = f"{basis_url()}/search?{parameter}"
    anfrage = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "de"})

    with _schloss:
        wartezeit = _letzte_anfrage + _min_intervall() - time.monotonic()
        if wartezeit > 0:
            time.sleep(wartezeit)

        try:
            with urlopen(anfrage, timeout=TIMEOUT_SEKUNDEN) as antwort:
                treffer = json.loads(antwort.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"Geocoder nicht erreichbar ({basis_url()}): {e}")
            raise GeocoderNichtErreichbar(str(e)) from e
        finally:
            _letzte_anfrage = time.monotonic()

    if not treffer:
        return None

    if not _plz_passt(adresse, treffer[0]):
        return None

    try:
        return float(treffer[0]["lat"]), float(treffer[0]["lon"])
    except (KeyError, IndexError, TypeError, ValueError):
        logger.warning(f"Unerwartete Antwort des Geocoders fuer '{adresse}'")
        return None


def _plz_passt(adresse: str, treffer: dict) -> bool:
    """
    Prueft, ob der Treffer in der angefragten Postleitzahl liegt.

    Die Freitextsuche von Nominatim raet lieber, als nichts zu liefern: auf
    eine erfundene Adresse antwortet sie mit irgendeinem entfernt aehnlichen
    Ort. Ein falscher Pin faellt auf einer Karte aber niemandem auf - er
    sieht genauso aus wie ein richtiger. Deshalb wird gegengeprueft.

    Nur ein *widersprechender* Treffer wird verworfen. Meldet der Dienst gar
    keine Postleitzahl, bleibt es beim Treffer: ein selbst gehosteter
    Geocoder liefert nicht zwingend dieselben Details.

    Verglichen werden die ersten drei Stellen, nicht alle fuenf. Deutsche
    Leitzahlen sind geografisch geordnet, die ersten drei Stellen umreissen
    damit die Stadt. Das faengt den Fall ab, der zaehlt - eine erfundene
    Adresse, auf die der Dienst mit irgendeinem Ort antwortet - laesst aber
    die Strasse gelten, die laut OSM einen Block weiter in der
    Nachbar-Leitzahl liegt. Sonst rutschte eine voellig richtige Anschrift
    ohne Not auf den Stadtmittelpunkt zurueck.
    """
    gefragt = re.search(r"\b\d{5}\b", adresse)
    if not gefragt:
        return True

    geliefert = (treffer.get("address") or {}).get("postcode")
    if not geliefert:
        return True

    geliefert = str(geliefert).strip()
    if gefragt.group(0)[:3] == geliefert[:3]:
        return True

    logger.info(
        f"Treffer verworfen: '{adresse}' erwartet {gefragt.group(0)}, "
        f"der Geocoder meldet {geliefert}"
    )
    return False


def _nachschlagen(adresse: str) -> Optional[Tuple[float, float]]:
    """Eine Adresse aufloesen - erst im Zwischenspeicher, dann beim Dienst."""
    schluessel = _normalisieren(adresse)
    if not schluessel:
        return None

    provider = basis_url()
    eintrag = get_cached(schluessel, provider)

    if eintrag:
        if eintrag["lat"] is not None and eintrag["lon"] is not None:
            return eintrag["lat"], eintrag["lon"]

        # Fehlschlag: nur wiederholen, wenn er alt genug ist
        if not _fehlschlag_abgelaufen(eintrag["resolved_at"]):
            return None

    koordinate = _abfragen(schluessel)
    store(schluessel, provider, *(koordinate or (None, None)))
    return koordinate


def _fehlschlag_abgelaufen(resolved_at: str) -> bool:
    """True, wenn ein gespeicherter Fehlschlag neu versucht werden darf."""
    try:
        gefragt_am = datetime.fromisoformat(resolved_at)
    except ValueError:
        return True

    if gefragt_am.tzinfo is None:
        gefragt_am = gefragt_am.replace(tzinfo=UTC)

    return datetime.now(UTC) - gefragt_am > timedelta(days=MISS_GUELTIG_TAGE)


def geocode(adresse: str, ort: Optional[str] = None) -> Optional[Dict]:
    """
    Loest eine Adresse auf, notfalls nur bis zum Ort.

    DFBnet-Adressen sind nicht immer vollstaendig - Spielstaetten stehen
    haeufig ohne Hausnummer da ("Karl-Liebknecht-Str., 07806 Neustadt an der
    Orla"). Findet der Geocoder die genaue Anschrift nicht, ist der
    Ortsmittelpunkt immer noch eine brauchbare Naeherung; die Karte
    kennzeichnet ihn als ungenau.

    Rueckgabe: {"lat", "lon", "genauigkeit": "adresse" | "ort"} oder None.
    """
    kandidaten: List[Tuple[str, str]] = [(adresse, "adresse")]

    grober_ort = ort or _ort_aus_adresse(adresse)
    if grober_ort and _normalisieren(grober_ort) != _normalisieren(adresse):
        kandidaten.append((grober_ort, "ort"))

    for kandidat, genauigkeit in kandidaten:
        if not kandidat or not kandidat.strip():
            continue
        koordinate = _nachschlagen(kandidat)
        if koordinate:
            return {"lat": koordinate[0], "lon": koordinate[1], "genauigkeit": genauigkeit}

    return None


def _ort_aus_adresse(adresse: str) -> Optional[str]:
    """
    Schneidet aus "Strasse, PLZ Ort" den hinteren Teil heraus.

    Spielstaetten kommen als eine Zeile aus DFBnet, Unparteiische dagegen mit
    getrenntem plz_ort - fuer die uebergibt der Aufrufer den Ort direkt.
    """
    if "," in adresse:
        return adresse.rsplit(",", 1)[-1].strip()

    # Kein Komma: wenigstens ab der Postleitzahl abschneiden
    treffer = re.search(r"\b\d{5}\b.*$", adresse)
    return treffer.group(0).strip() if treffer else None
