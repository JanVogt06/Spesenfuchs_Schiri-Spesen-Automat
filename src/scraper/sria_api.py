"""
Zugriff auf die JSON-Schnittstelle der Ansetzungs-App (Schiriansetzung).

Die App sria.dfbnet.org ist eine Angular-App, die alles von
https://api.dfbnet.org/api/referee/ laedt - die Ansetzungen, die Stammdaten,
die Qualifikationen und die Saisonstatistik. Die Module ansetzungen,
saisons und stammdaten stellen genau die Abrufe, die die App selbst macht,
statt deren Oberflaeche zu lesen.

Anders als die Spielbericht-App authentisiert diese Schnittstelle nicht ueber
ein Cookie, sondern mit dem Bearer-Token, den die App nach dem Anmelden im
sessionStorage ablegt. Er lebt nur wenige Minuten, die App erneuert ihn
selbst - deshalb wird er vor jedem Abruf frisch gelesen.

Sicherheitsnetz wie bei den Spielberichten: jeder Abruf geht durch
_pruefe_abruf. Erlaubt sind nur die Lese-Pfade unten; alles, was die App zum
Bestaetigen, Zuruecksenden oder Aendern benutzt, kann hier nicht entstehen.
"""
import re
from datetime import date
from typing import Dict, Iterable, List
from urllib.parse import urlencode, urlparse

from playwright.sync_api import Page

_ZEITLIMIT_MS = 45000

_API = "https://api.dfbnet.org/api/referee/"

_ID = r"[A-Za-z0-9]{1,64}"
# (Methode, Pfad ohne Query) - alles andere wird gar nicht erst abgeschickt
_ERLAUBT = [
    ("GET", re.compile(r"appointment/with-action-state")),
    ("GET", re.compile(r"appointment/with-match-details")),
    ("GET", re.compile(r"appointment/summary")),
    ("GET", re.compile(r"match")),
    ("GET", re.compile(r"club-team")),
    ("GET", re.compile(rf"league/{_ID}")),
    ("GET", re.compile(r"season")),
    ("GET", re.compile(rf"referee/{_ID}")),
    ("GET", re.compile(rf"referee/{_ID}/qualification")),
    ("GET", re.compile(rf"referee/{_ID}/additional-qualification")),
    ("GET", re.compile(rf"referee/{_ID}/exemption/summary")),
    ("GET", re.compile(rf"referee-id-card/{_ID}")),
    # Ein POST, der nur liest: Spielstaetten zu einer Liste von IDs
    ("POST", re.compile(r"venue/query")),
]

# So viele IDs je Abruf - haelt die URL kurz
BLOCK = 50


class SitzungAbgelaufen(RuntimeError):
    """Kein gueltiger Token (401/403) - die App ist nicht (mehr) angemeldet."""


def _pruefe_abruf(methode: str, pfad: str) -> str:
    ohne_query = pfad.split("?", 1)[0]
    if not any(m == methode and muster.fullmatch(ohne_query) for m, muster in _ERLAUBT):
        raise ValueError(f"Abruf {methode} {ohne_query!r} ist nicht freigegeben")
    return _API + pfad


# Laeuft im Kontext der Ansetzungs-App. Der Token wird bei jedem Abruf neu
# gelesen, weil die App ihn alle paar Minuten erneuert.
_ABRUF_JS = """
    async ({url, methode, body}) => {
        const token = sessionStorage.getItem('access_token');
        if (!token) return {status: 401};
        const headers = {Authorization: 'Bearer ' + token, Accept: 'application/json'};
        if (body !== null) headers['Content-Type'] = 'application/json';
        let antwort;
        try {
            antwort = await fetch(url, {
                method: methode, headers, body: body === null ? undefined : JSON.stringify(body),
            });
        } catch (fehler) {
            // Kein Status: Netzwerkfehler, oder ein Gateway-Timeout ohne
            // CORS-Kopfzeilen, den der Browser nicht durchreicht
            return {status: 0};
        }
        if (!antwort.ok) return {status: antwort.status};
        return {status: antwort.status, daten: await antwort.json()};
    }
"""

# Fertig angemeldet ist die App, sobald sie einen Token hat und auf der
# Seite eines Schiedsrichters steht - die URL traegt dessen ID.
_APP_BEREIT_JS = r"""
    () => !!sessionStorage.getItem('access_token')
          && /\/referee\/[A-Za-z0-9]+/.test(location.pathname)
"""


class Serverfehler(RuntimeError):
    """Die Schnittstelle antwortet mit 5xx."""


def abruf(page: Page, methode: str, pfad: str, body=None, wiederholen: bool = True):
    """
    Ein Abruf gegen die Schnittstelle; liefert die JSON-Antwort.

    Args:
        wiederholen: bei 5xx einmal nach kurzer Pause wiederholen. Lohnt
            sich meist: der Server cacht, was er beim ersten Versuch
            aufgebaut hat (siehe saisons._SEITE).
    """
    url = _pruefe_abruf(methode, pfad)
    kurz = pfad.split("?", 1)[0]

    for versuch in (1, 2):
        ergebnis = page.evaluate(_ABRUF_JS, {"url": url, "methode": methode, "body": body})
        status = ergebnis.get("status")
        if status == 200:
            return ergebnis.get("daten")
        if status in (401, 403) and versuch == 1:
            # Der Token kann genau in diesem Moment erneuert werden
            page.wait_for_timeout(2000)
            continue
        if status in (401, 403):
            raise SitzungAbgelaufen(f"HTTP {status} auf {kurz}")
        # 0: keine Antwort (siehe _ABRUF_JS) - fuer den Aufrufer wie ein 5xx
        if status in (0, 500, 502, 503, 504):
            if versuch == 1 and wiederholen:
                page.wait_for_timeout(3000)
                continue
            raise Serverfehler(f"HTTP {status} auf {kurz}")
        raise RuntimeError(f"HTTP {status} auf {kurz}")


def warte_auf_app(page: Page) -> str:
    """Wartet, bis die App angemeldet ist, und liefert die eigene Schiedsrichter-ID."""
    page.wait_for_function(_APP_BEREIT_JS, timeout=_ZEITLIMIT_MS, polling=250)
    treffer = re.search(r"/referee/([A-Za-z0-9]+)", urlparse(page.url).path)
    if not treffer:
        raise RuntimeError("Schiedsrichter-ID nicht in der Adresse der Ansetzungs-App")
    return treffer.group(1)


def iso(tag: date) -> str:
    return f"{tag.isoformat()}T00:00:00.000Z"


def bloecke(ids: Iterable[str]) -> List[List[str]]:
    eindeutig = list(dict.fromkeys(i for i in ids if i))
    return [eindeutig[i:i + BLOCK] for i in range(0, len(eindeutig), BLOCK)]


def hole_nach_ids(page: Page, pfad: str, parameter: str, ids: Iterable[str]) -> Dict[str, Dict]:
    """Eintraege zu vielen IDs, blockweise abgefragt; id -> Eintrag."""
    ergebnis = {}
    for block in bloecke(ids):
        query = urlencode([(parameter, i) for i in block])
        for eintrag in abruf(page, "GET", f"{pfad}?{query}") or []:
            ergebnis[eintrag["id"]] = eintrag
    return ergebnis


def team_namen(page: Page, spiel_ids: Iterable[str]) -> Dict[str, Dict]:
    """
    Spiele (match) zu IDs, und die Teams dazu (club-team) - in zwei Schritten,
    weil das Spiel nur die Team-IDs traegt.

    Returns:
        {"spiele": id -> Spiel, "teams": id -> Team}
    """
    spiele = hole_nach_ids(page, "match", "match-ids", spiel_ids)
    team_ids = [t for s in spiele.values() for t in (s.get("homeTeamId"), s.get("guestTeamId"))]
    teams = hole_nach_ids(page, "club-team", "club-team-ids", team_ids)
    return {"spiele": spiele, "teams": teams}


def text(wert) -> str:
    return "" if wert is None else str(wert).strip()


def datum_de(iso_datum) -> str:
    """'2019-01-26' -> '26.01.2019'; leer bleibt leer."""
    if not iso_datum:
        return ""
    jahr, monat, tag = str(iso_datum)[:10].split("-")
    return f"{tag}.{monat}.{jahr}"
