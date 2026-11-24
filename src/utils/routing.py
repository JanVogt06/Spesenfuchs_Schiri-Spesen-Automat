"""
Strassenentfernungen ueber einen OSRM-Routenplaner.

Voreinstellung ist der Dienst von OpenStreetMap Deutschland (FOSSGIS e.V.),
den auch openstreetmap.org zur Routenplanung nutzt. ROUTING_URL zeigt auf
einen eigenen OSRM, wenn gewuenscht - etwa, damit keine Koordinate das Haus
verlaesst. Gefragt wird ueber die Matrix-Schnittstelle (table): eine Anfrage
liefert alle Wege zwischen mehreren Punkten, fuer ein ganzes Gespann also
eine einzige.

Wie beim Geocoder gilt: hoechstens eine Anfrage je Sekunde
(ROUTING_MIN_INTERVAL), und jede Strecke wird nur einmal gefragt
(db.strecken). Uebertragen werden nur Koordinaten, keine Namen oder
Anschriften.
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

# Wie beim Geocoder: ein Weg, den heute niemand kennt, ist in vier Wochen vielleicht eingetragen
MISS_GUELTIG_TAGE = 30

# OSRM nimmt je Matrix-Anfrage hoechstens 100 Punkte an (max-table-size)
MAX_PUNKTE_JE_ANFRAGE = 100

# Luftlinie -> Strasse: auf Landstrassen in Thueringen faehrt man im Mittel
# ein gutes Drittel mehr als die Luftlinie. Nur Notbehelf, wenn der
# Routenplaner nicht antwortet.
UMWEGFAKTOR = 1.3

_schloss = threading.Lock()
_letzte_anfrage = 0.0


class RoutingNichtErreichbar(Exception):
    """Der Routenplaner hat nicht (brauchbar) geantwortet."""


def basis_url() -> str:
    return (os.getenv("ROUTING_URL") or STANDARD_URL).rstrip("/")


def _min_intervall() -> float:
    try:
        return max(0.0, float(os.getenv("ROUTING_MIN_INTERVAL", "1.0")))
    except ValueError:
        return 1.0


def runden(punkt: Punkt) -> Punkt:
    """Schluessel im Zwischenspeicher: gut zehn Meter genau."""
    return round(punkt[0], 4), round(punkt[1], 4)


def luftlinie_m(a: Punkt, b: Punkt) -> float:
    """Entfernung auf der Kugel in Metern (Haversine)."""
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
    """Eine table-Anfrage: Meter von jeder Quelle zu jedem Ziel, None ohne Weg."""
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
    Ergebnis von entfernungen(): meter[i][j] von Quelle i zu Ziel j.

    None heisst: unbekannt - der Dienst kennt keinen Weg, oder die Strecke
    wurde nicht gefragt, weil das Zeitbudget aufgebraucht war (dann zaehlt
    sie in offen und kommt beim naechsten Aufruf dran).
    """

    def __init__(self, meter: List[List[Optional[float]]], offen: int):
        self.meter = meter
        self.offen = offen


def entfernungen(quellen: Sequence[Punkt], ziele: Sequence[Punkt],
                 frist: Optional[float] = None) -> Entfernungen:
    """
    Strassenentfernungen von jeder Quelle zu jedem Ziel, in Metern.

    Was im Zwischenspeicher steht, kommt von dort; der Rest geht in so wenigen
    Anfragen wie moeglich an den Routenplaner. frist ist ein Zeitpunkt
    (time.monotonic), nach dem keine neue Anfrage mehr beginnt.

    Antwortet der Dienst nicht, fliegt RoutingNichtErreichbar - der Aufrufer
    entscheidet, ob er auf die Luftlinie ausweicht.
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
                if (q, z) in paare:
                    meter[(q, z)] = antwort[i][j]
                    neu.append((q, z, antwort[i][j]))
        store_strecken(neu, provider)

    return Entfernungen([[meter.get((q, z)) for z in ziele] for q in quellen], offen)


def _anfragen_buendeln(fehlend: List[Tuple[Punkt, Punkt]]):
    """
    Fasst fehlende Strecken zu Matrix-Anfragen zusammen: je Quelle alle ihre
    fehlenden Ziele, und Quellen mit denselben Zielen gemeinsam. Keine Anfrage
    ueberschreitet MAX_PUNKTE_JE_ANFRAGE.
    """
    ziele_je_quelle: Dict[Punkt, List[Punkt]] = {}
    for q, z in fehlend:
        ziele_je_quelle.setdefault(q, []).append(z)

    nach_zielen: Dict[Tuple[Punkt, ...], List[Punkt]] = {}
    for q, zs in ziele_je_quelle.items():
        nach_zielen.setdefault(tuple(zs), []).append(q)

    for zs, qs in nach_zielen.items():
        # Viele Quellen zu einem Ziel (Spielorte -> Wohnort) oder umgekehrt:
        # in Bloecke teilen, die zusammen unter die Grenze passen
        platz = MAX_PUNKTE_JE_ANFRAGE // 2
        for i in range(0, len(qs), platz):
            for j in range(0, len(zs), platz):
                block_q, block_z = qs[i:i + platz], list(zs[j:j + platz])
                yield block_q, block_z, {(q, z) for q in block_q for z in block_z}
