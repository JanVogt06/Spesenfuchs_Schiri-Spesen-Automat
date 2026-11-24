"""
Address -> coordinate, via Nominatim.

Only what is not already in the database (db.geocode) is requested. This is
not an optimisation but the operating basis: the public Nominatim service
allows one request per second from a single thread and forbids bulk
queries. With the cache it stays at an estimated hundred requests over the
lifetime of an account - one's own address is a single one, colleagues and
venues repeat.

NOMINATIM_URL points to a self-hosted service if desired; the default is
the public one. A self-hosted service may be queried faster, which is what
GEOCODER_MIN_INTERVAL is for.

Deliberately urllib instead of requests/httpx: a single GET request does not
justify an additional dependency.
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
from db.geocode import get_cached, get_ortsname, store, store_ortsname
from utils.logger import setup_logger

logger = setup_logger("geocoder")

STANDARD_URL = "https://nominatim.openstreetmap.org"

# After this time an unsuccessful address is tried again. OSM keeps
# growing; what nobody knows today may have been added in four weeks.
MISS_GUELTIG_TAGE = 30

# Nominatim requires a descriptive User-Agent with a way to get in touch.
# Without it the public service answers with 403.
USER_AGENT = f"Spesenfuchs/{APP_VERSION} (+https://github.com/JanVogt06/dfb-spesen-generator)"

TIMEOUT_SEKUNDEN = 10

# Serialises all requests of this process. The map resolves up to four
# addresses at once, and several maps can be open at the same time -
# without the lock those would be parallel requests to a service that
# explicitly demands a single thread.
_schloss = threading.Lock()
_letzte_anfrage = 0.0


class GeocoderNichtErreichbar(Exception):
    """The service did not respond - as opposed to "address unknown"."""


def basis_url() -> str:
    """The configured service, without a trailing slash."""
    return (os.getenv("NOMINATIM_URL") or STANDARD_URL).rstrip("/")


def _min_intervall() -> float:
    """Minimum interval between two requests to the same service."""
    try:
        return max(0.0, float(os.getenv("GEOCODER_MIN_INTERVAL", "1.0")))
    except ValueError:
        return 1.0


def _normalisieren(adresse: str) -> str:
    """Normalises the key under which an address is cached."""
    return re.sub(r"\s+", " ", adresse).strip(" ,").lower()


def _abfragen(adresse: str) -> Optional[Tuple[float, float]]:
    """
    One request to the geocoder, observing the minimum interval.

    Returns None if the service does not know the address. If it does not
    respond at all, GeocoderNichtErreichbar is raised - that must not end up
    in the cache as "address unknown".
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
    Checks whether the hit lies in the requested postcode.

    Nominatim's free-text search would rather guess than return nothing: for
    an invented address it answers with some vaguely similar place. A wrong
    pin goes unnoticed on a map, though - it looks exactly like a right one.
    That is why the result is cross-checked.

    Only a *contradicting* hit is discarded. If the service reports no
    postcode at all, the hit stands: a self-hosted geocoder does not
    necessarily return the same details.

    The first three digits are compared, not all five. German postcodes are
    geographically ordered, so the first three digits outline the city. This
    catches the case that matters - an invented address to which the service
    answers with some place - but still accepts the street that, according
    to OSM, lies one block over in the neighbouring postcode. Otherwise a
    perfectly correct address would needlessly fall back to the city
    centre.
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
    """Resolve an address - first in the cache, then at the service."""
    schluessel = _normalisieren(adresse)
    if not schluessel:
        return None

    provider = basis_url()
    eintrag = get_cached(schluessel, provider)

    if eintrag:
        if eintrag["lat"] is not None and eintrag["lon"] is not None:
            return eintrag["lat"], eintrag["lon"]

        # Failure: only retry if it is old enough
        if not _fehlschlag_abgelaufen(eintrag["resolved_at"]):
            return None

    koordinate = _abfragen(schluessel)
    store(schluessel, provider, *(koordinate or (None, None)))
    return koordinate


def _fehlschlag_abgelaufen(resolved_at: str) -> bool:
    """True if a stored failure may be retried."""
    try:
        gefragt_am = datetime.fromisoformat(resolved_at)
    except ValueError:
        return True

    if gefragt_am.tzinfo is None:
        gefragt_am = gefragt_am.replace(tzinfo=UTC)

    return datetime.now(UTC) - gefragt_am > timedelta(days=MISS_GUELTIG_TAGE)


def geocode(adresse: str, ort: Optional[str] = None) -> Optional[Dict]:
    """
    Resolves an address, if necessary only down to the town.

    DFBnet addresses are not always complete - venues often come without a
    house number ("Karl-Liebknecht-Str., 07806 Neustadt an der Orla"). If
    the geocoder does not find the exact address, the town centre is still
    a usable approximation; the map marks it as imprecise.

    Returns: {"lat", "lon", "genauigkeit": "adresse" | "ort"} or None.
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


def geocode_bekannt(adresse: str, ort: Optional[str] = None) -> Tuple[Optional[Dict], bool]:
    """
    Like geocode, but only from the cache - without any request.

    Returns (hit or None, offen). offen means: at least one level has never
    been asked (or was unsuccessful too long ago), so a call to geocode()
    might still find something. Meant for evaluations over many addresses
    that must not query the public service in one go.
    """
    kandidaten: List[Tuple[str, str]] = [(adresse, "adresse")]
    grober_ort = ort or _ort_aus_adresse(adresse)
    if grober_ort and _normalisieren(grober_ort) != _normalisieren(adresse):
        kandidaten.append((grober_ort, "ort"))

    provider = basis_url()
    for kandidat, genauigkeit in kandidaten:
        schluessel = _normalisieren(kandidat or "")
        if not schluessel:
            continue
        eintrag = get_cached(schluessel, provider)
        if not eintrag or (eintrag["lat"] is None and _fehlschlag_abgelaufen(eintrag["resolved_at"])):
            return None, True
        if eintrag["lat"] is not None and eintrag["lon"] is not None:
            return {"lat": eintrag["lat"], "lon": eintrag["lon"], "genauigkeit": genauigkeit}, False

    return None, False


def _ort_aus_adresse(adresse: str) -> Optional[str]:
    """
    Cuts the trailing part out of "Street, postcode Town".

    Venues come from DFBnet as a single line, referees on the other hand with
    a separate plz_ort - for those the caller passes the town directly.
    """
    if "," in adresse:
        return adresse.rsplit(",", 1)[-1].strip()

    # No comma: at least cut from the postcode onwards
    treffer = re.search(r"\b\d{5}\b.*$", adresse)
    return treffer.group(0).strip() if treffer else None


# Address parts that name a place, most specific first. Suburbs come after
# villages and towns: "near Jena" helps more than "near Lobeda-West".
_ORTSTEILE = ("village", "town", "city", "municipality", "suburb", "hamlet")


def ortsname(lat: float, lon: float) -> Optional[str]:
    """
    Name of the village or town around a coordinate (reverse geocoding), or None.

    Used to describe meeting points ("near Kahla"). The coordinate is not an
    address of anyone - just a point on the way. Results, including "nothing
    found", are kept in ortsnamen_cache; an unreachable service is not
    cached and simply yields None, the suggestion is shown without a name.
    """
    global _letzte_anfrage

    schluessel = (round(lat, 3), round(lon, 3))
    provider = basis_url()
    eintrag = get_ortsname(*schluessel, provider)
    if eintrag and (eintrag["name"] is not None or not _fehlschlag_abgelaufen(eintrag["resolved_at"])):
        return eintrag["name"]

    parameter = urlencode({"lat": f"{schluessel[0]:.3f}", "lon": f"{schluessel[1]:.3f}",
                           "format": "jsonv2", "zoom": "14", "addressdetails": "1"})
    anfrage = Request(f"{provider}/reverse?{parameter}", headers={"User-Agent": USER_AGENT, "Accept-Language": "de"})

    with _schloss:
        wartezeit = _letzte_anfrage + _min_intervall() - time.monotonic()
        if wartezeit > 0:
            time.sleep(wartezeit)
        try:
            with urlopen(anfrage, timeout=TIMEOUT_SEKUNDEN) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"Geocoder nicht erreichbar ({provider}): {e}")
            return None
        finally:
            _letzte_anfrage = time.monotonic()

    adresse = (daten.get("address") or {}) if isinstance(daten, dict) else {}
    name = next((adresse[teil] for teil in _ORTSTEILE if adresse.get(teil)), None)
    store_ortsname(*schluessel, provider, name)
    return name
