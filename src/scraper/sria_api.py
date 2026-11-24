"""
Access to the JSON interface of the assignment app (Schiriansetzung).

The app sria.dfbnet.org is an Angular app that loads everything from
https://api.dfbnet.org/api/referee/ - the assignments, the master data
(Stammdaten), the qualifications and the season statistics. The modules
ansetzungen, saisons and stammdaten make exactly the requests the app itself
makes, instead of reading its user interface.

Unlike the match report app, this interface does not authenticate via a
cookie but with the bearer token that the app stores in sessionStorage after
login. It only lives for a few minutes and the app renews it itself - that is
why it is read afresh before every request.

Safety net as with the match reports: every request goes through
_pruefe_abruf. Only the read paths below are allowed; anything the app uses
to confirm, send back or change cannot arise here.
"""
import re
from datetime import date
from typing import Dict, Iterable, List
from urllib.parse import urlencode, urlparse

from playwright.sync_api import Page

_ZEITLIMIT_MS = 45000

_API = "https://api.dfbnet.org/api/referee/"

_ID = r"[A-Za-z0-9]{1,64}"
# (method, path without query) - anything else is never even sent
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
    # A POST that only reads: venues (Spielstaetten) for a list of IDs
    ("POST", re.compile(r"venue/query")),
]

# This many IDs per request - keeps the URL short
BLOCK = 50


class SitzungAbgelaufen(RuntimeError):
    """No valid token (401/403) - the app is not (or no longer) logged in."""


def _pruefe_abruf(methode: str, pfad: str) -> str:
    ohne_query = pfad.split("?", 1)[0]
    if not any(m == methode and muster.fullmatch(ohne_query) for m, muster in _ERLAUBT):
        raise ValueError(f"Abruf {methode} {ohne_query!r} ist nicht freigegeben")
    return _API + pfad


# Runs in the context of the assignment app. The token is read anew on every
# request because the app renews it every few minutes.
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
            // No status: network error, or a gateway timeout without CORS
            // headers, which the browser does not pass through
            return {status: 0};
        }
        if (!antwort.ok) return {status: antwort.status};
        return {status: antwort.status, daten: await antwort.json()};
    }
"""

# The app is fully logged in as soon as it has a token and is on a referee's
# page - the URL carries that referee's ID.
_APP_BEREIT_JS = r"""
    () => !!sessionStorage.getItem('access_token')
          && /\/referee\/[A-Za-z0-9]+/.test(location.pathname)
"""


class Serverfehler(RuntimeError):
    """The interface responds with 5xx."""


def abruf(page: Page, methode: str, pfad: str, body=None, wiederholen: bool = True):
    """
    A request against the interface; returns the JSON response.

    Args:
        wiederholen: on 5xx, retry once after a short pause. Usually worth
            it: the server caches what it built up on the first attempt (see
            saisons._SEITE).
    """
    url = _pruefe_abruf(methode, pfad)
    kurz = pfad.split("?", 1)[0]

    for versuch in (1, 2):
        ergebnis = page.evaluate(_ABRUF_JS, {"url": url, "methode": methode, "body": body})
        status = ergebnis.get("status")
        if status == 200:
            return ergebnis.get("daten")
        if status in (401, 403) and versuch == 1:
            # The token may be renewed at exactly this moment
            page.wait_for_timeout(2000)
            continue
        if status in (401, 403):
            raise SitzungAbgelaufen(f"HTTP {status} auf {kurz}")
        # 0: no response (see _ABRUF_JS) - same as a 5xx for the caller
        if status in (0, 500, 502, 503, 504):
            if versuch == 1 and wiederholen:
                page.wait_for_timeout(3000)
                continue
            raise Serverfehler(f"HTTP {status} auf {kurz}")
        raise RuntimeError(f"HTTP {status} auf {kurz}")


def warte_auf_app(page: Page) -> str:
    """Waits until the app is logged in and returns the user's own referee ID."""
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
    """Entries for many IDs, queried in blocks; id -> entry."""
    ergebnis = {}
    for block in bloecke(ids):
        query = urlencode([(parameter, i) for i in block])
        for eintrag in abruf(page, "GET", f"{pfad}?{query}") or []:
            ergebnis[eintrag["id"]] = eintrag
    return ergebnis


def team_namen(page: Page, spiel_ids: Iterable[str]) -> Dict[str, Dict]:
    """
    Matches (match) for IDs, and the teams for them (club-team) - in two
    steps, because the match only carries the team IDs.

    Returns:
        {"spiele": id -> match, "teams": id -> team}
    """
    spiele = hole_nach_ids(page, "match", "match-ids", spiel_ids)
    team_ids = [t for s in spiele.values() for t in (s.get("homeTeamId"), s.get("guestTeamId"))]
    teams = hole_nach_ids(page, "club-team", "club-team-ids", team_ids)
    return {"spiele": spiele, "teams": teams}


def text(wert) -> str:
    return "" if wert is None else str(wert).strip()


def datum_de(iso_datum) -> str:
    """'2019-01-26' -> '26.01.2019'; empty stays empty."""
    if not iso_datum:
        return ""
    jahr, monat, tag = str(iso_datum)[:10].split("-")
    return f"{tag}.{monat}.{jahr}"
