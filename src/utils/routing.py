"""
Road distances via an OSRM routing service.

The default is the service of OpenStreetMap Germany (FOSSGIS e.V.), which
openstreetmap.org also uses for route planning. ROUTING_URL can point to
a self-hosted OSRM if desired - for instance, so that no coordinate leaves
the house. Queries go through the matrix interface (table): one request
returns all routes between several points, so a whole crew needs just
one.

As with the geocoder: at most one request per second
(ROUTING_MIN_INTERVAL), and each route is only ever asked for once
(db.strecken). Only coordinates are transmitted, no names or
addresses.
"""
import json
import math
import os
import threading
import time
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from db.strecken import Punkt, get_strecken, store_strecken
from utils.geocoder import USER_AGENT
from utils.logger import setup_logger

logger = setup_logger("routing")

STANDARD_URL = "https://routing.openstreetmap.de/routed-car"
TIMEOUT_SEKUNDEN = 15

# As with the geocoder: a route nobody knows today may have been added in four weeks
MISS_GUELTIG_TAGE = 30

# OSRM accepts at most 100 points per matrix request (max-table-size)
MAX_PUNKTE_JE_ANFRAGE = 100

# Straight line -> road: on country roads in Thuringia you drive on average
# a good third more than the straight-line distance. Only a stopgap when the
# routing service does not respond.
UMWEGFAKTOR = 1.3

_schloss = threading.Lock()
_letzte_anfrage = 0.0


class RoutingNichtErreichbar(Exception):
    """The routing service did not respond (or not usefully)."""


def basis_url() -> str:
    return (os.getenv("ROUTING_URL") or STANDARD_URL).rstrip("/")


def _min_intervall() -> float:
    try:
        return max(0.0, float(os.getenv("ROUTING_MIN_INTERVAL", "1.0")))
    except ValueError:
        return 1.0


def runden(punkt: Punkt) -> Punkt:
    """Cache key: accurate to a little over ten metres."""
    return round(punkt[0], 4), round(punkt[1], 4)


def luftlinie_m(a: Punkt, b: Punkt) -> float:
    """Distance on the sphere in metres (haversine)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _abgelaufen(resolved_at: str) -> bool:
    try:
        zeitpunkt = datetime.fromisoformat(resolved_at)
    except ValueError:
        return True
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=UTC)
    return datetime.now(UTC) - zeitpunkt > timedelta(days=MISS_GUELTIG_TAGE)


def _matrix_abfragen(quellen: List[Punkt], ziele: List[Punkt]) -> List[List[Optional[float]]]:
    """One table request: metres from each source to each destination, None if there is no route."""
    global _letzte_anfrage

    punkte = quellen + ziele
    koordinaten = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in punkte)
    sources = ";".join(str(i) for i in range(len(quellen)))
    destinations = ";".join(str(i) for i in range(len(quellen), len(punkte)))
    url = (f"{basis_url()}/table/v1/driving/{koordinaten}"
           f"?annotations=distance&sources={sources}&destinations={destinations}")
    anfrage = Request(url, headers={"User-Agent": USER_AGENT})

    with _schloss:
        wartezeit = _letzte_anfrage + _min_intervall() - time.monotonic()
        if wartezeit > 0:
            time.sleep(wartezeit)
        try:
            with urlopen(anfrage, timeout=TIMEOUT_SEKUNDEN) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"Routenplaner nicht erreichbar ({basis_url()}): {e}")
            raise RoutingNichtErreichbar(str(e)) from e
        finally:
            _letzte_anfrage = time.monotonic()

    matrix = daten.get("distances") if isinstance(daten, dict) else None
    if daten.get("code") != "Ok" or not isinstance(matrix, list) or len(matrix) != len(quellen):
        logger.warning(f"Unerwartete Antwort des Routenplaners: {str(daten)[:200]}")
        raise RoutingNichtErreichbar("unerwartete Antwort")

    ergebnis = []
    for zeile in matrix:
        if not isinstance(zeile, list) or len(zeile) != len(ziele):
            raise RoutingNichtErreichbar("unerwartete Antwort")
        ergebnis.append([float(m) if isinstance(m, (int, float)) and not isinstance(m, bool) else None
                         for m in zeile])
    return ergebnis


class Entfernungen:
    """
    Result of entfernungen(): meter[i][j] from source i to destination j.

    None means unknown - the service knows no route, or the route was not
    requested because the time budget was used up (it then counts towards
    offen and is picked up on the next call).
    """

    def __init__(self, meter: List[List[Optional[float]]], offen: int):
        self.meter = meter
        self.offen = offen


def entfernungen(quellen: Sequence[Punkt], ziele: Sequence[Punkt],
                 frist: Optional[float] = None) -> Entfernungen:
    """
    Road distances from each source to each destination, in metres.

    Whatever is in the cache comes from there; the rest goes to the routing
    service in as few requests as possible. frist is a point in time
    (time.monotonic) after which no new request is started.

    If the service does not respond, RoutingNichtErreichbar is raised - the
    caller decides whether to fall back to the straight-line distance.
    """
    quellen = [runden(p) for p in quellen]
    ziele = [runden(p) for p in ziele]
    provider = basis_url()

    gespeichert = get_strecken(((q, z) for q in quellen for z in ziele if q != z), provider)
    meter: Dict[Tuple[Punkt, Punkt], Optional[float]] = {}
    fehlend = []
    for q in quellen:
        for z in ziele:
            if q == z:
                meter[(q, z)] = 0.0
                continue
            eintrag = gespeichert.get((q, z))
            if eintrag and (eintrag["meter"] is not None or not _abgelaufen(eintrag["resolved_at"])):
                meter[(q, z)] = eintrag["meter"]
            else:
                fehlend.append((q, z))

    offen = 0
    for gruppe_q, gruppe_z, paare in _anfragen_buendeln(fehlend):
        if frist is not None and time.monotonic() >= frist:
            offen += len(paare)
            continue
        antwort = _matrix_abfragen(gruppe_q, gruppe_z)
        neu = []
        for i, q in enumerate(gruppe_q):
            for j, z in enumerate(gruppe_z):
                if q == z:
                    continue
                if (q, z) in paare:
                    meter[(q, z)] = antwort[i][j]
                # Keep the routes that came along - they will be needed for the next match
                neu.append((q, z, antwort[i][j]))
        store_strecken(neu, provider)

    return Entfernungen([[meter.get((q, z)) for z in ziele] for q in quellen], offen)


def _anfragen_buendeln(fehlend: List[Tuple[Punkt, Punkt]]):
    """
    Combines missing routes into as few matrix requests as possible:
    all affected sources against all affected destinations. This also yields
    a few routes nobody asked for - but for a crew it is one request instead
    of one per person, and each one takes a few seconds on the public
    service. No request exceeds MAX_PUNKTE_JE_ANFRAGE.
    """
    quellen = list(dict.fromkeys(q for q, _ in fehlend))
    ziele = list(dict.fromkeys(z for _, z in fehlend))
    gesucht = set(fehlend)

    platz = MAX_PUNKTE_JE_ANFRAGE // 2
    for i in range(0, len(quellen), platz):
        for j in range(0, len(ziele), platz):
            block_q, block_z = quellen[i:i + platz], ziele[j:j + platz]
            paare = {(q, z) for q in block_q for z in block_z if (q, z) in gesucht}
            if paare:
                yield block_q, block_z, paare
