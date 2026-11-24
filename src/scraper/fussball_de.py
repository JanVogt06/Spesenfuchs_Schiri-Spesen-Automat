"""
League tables from fussball.de.

They are needed for two things: the *Ligen* tab and the expenses of cup
matches and friendlies. For both, the rate does not depend on the league level
of the match but on that of the participating teams (§2 para. 3 and 4 of the
expense regulations, Spesenordnung), and that is not contained in the
assignment data from DFBnet.

The pages are rendered server-side and readable without login, so urllib is
enough - as with the geocoder, that does not justify an additional dependency.
fussball.de's robots.txt allows everything except /*-service/ and /tipply/.

The division identifiers (Staffel-Kennungen) are NOT hard-wired: they change
every season. Instead they are discovered (see entdecke_staffeln) - starting
from a club that the user's own assignments already know plays in the league
in question. This is self-checking: the slug of a division names the league
level, team type and association, so only the right division can come out, or
none at all.
"""
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, replace
from html import unescape
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote_plus
from urllib.request import Request, urlopen

from core.config import APP_VERSION
from utils.logger import setup_logger

logger = setup_logger("fussball_de")

BASIS_URL = "https://www.fussball.de"

USER_AGENT = f"Spesenfuchs/{APP_VERSION} (+https://github.com/JanVogt06/dfb-spesen-generator)"

TIMEOUT_SEKUNDEN = 20

# Minimum interval between two requests. fussball.de does not state a number,
# but a nightly run over a handful of divisions must not look like a load
# attack.
MIN_INTERVALL = 1.0

_schloss = threading.Lock()
_letzte_anfrage = 0.0


class FussballDeNichtErreichbar(Exception):
    """The page did not respond - as opposed to "nothing found"."""


@dataclass(frozen=True)
class Staffel:
    """A league-level division (Staffel) on fussball.de."""
    staffel_id: str
    pfad: str            # full path incl. slug, without base URL
    slug: str
    spielklasse: str     # from the slug, e.g. "verbandsliga"
    verband: str         # from the slug, e.g. "thueringen"
    anzeigename: str     # e.g. "11Teamsports Thüringenliga"

    @property
    def url(self) -> str:
        return f"{BASIS_URL}{self.pfad}"


@dataclass(frozen=True)
class Tabellenplatz:
    """One row of a league table."""
    platz: int
    mannschaft: str
    team_id: str
    spiele: int
    siege: int
    unentschieden: int
    niederlagen: int
    tore: int
    gegentore: int
    punkte: int


def _hole(url: str) -> str:
    """Fetches a page, with a minimum interval since the previous request."""
    global _letzte_anfrage

    with _schloss:
        wartezeit = MIN_INTERVALL - (time.monotonic() - _letzte_anfrage)
        if wartezeit > 0:
            time.sleep(wartezeit)

        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}),
                         timeout=TIMEOUT_SEKUNDEN) as antwort:
                return antwort.read().decode("utf-8", "replace")
        except (HTTPError, URLError, TimeoutError, OSError) as fehler:
            raise FussballDeNichtErreichbar(f"{url}: {fehler}") from fehler
        finally:
            _letzte_anfrage = time.monotonic()


# ===== Making names comparable =====

# Only the marker of a Spielgemeinschaft (joint team) is cut off: DFBnet
# writes "SG SV Alach I", fussball.de "SV Alach". Everything else stays.
#
# Measured against the real names in this data set: if the legal forms (SV,
# FC, ...) and years are additionally dropped, two more matches are made -
# among them, however, "SG Saalfeld 46 e.V." -> "FC Saalfeld", i.e. two
# different clubs of the same town. Two more matches are not worth that
# error.
_SPIELGEMEINSCHAFT = {"sg", "spg"}

_NUMMER_ROEMISCH = {"i": 1, "ii": 2, "iii": 3, "iv": 4}

# Roman numeral, Arabic number or "2." at the end of the name.
_NUMMER_AM_ENDE = re.compile(r"(?:^|[\s(])(i{1,3}|iv|[2-9])\s*\.?\s*$")


def mannschaftsnummer(name: str) -> int:
    """
    The number of the team within its club.

    DFBnet writes "SG SV Alach I", "FC Union Erfurt II" or "SV 09 Arnstadt 2.",
    fussball.de "FC Empor Weimar 06 2.". Without a number the first team is
    meant.

    This number is the most important part of the comparison: the third team
    of FC Saalfeld plays Kreisliga, the first Verbandsliga. Whoever throws the
    number away confuses 25 euros with 50.
    """
    treffer = _NUMMER_AM_ENDE.search((name or "").strip().lower())
    if not treffer:
        return 1

    gefunden = treffer.group(1)

    return _NUMMER_ROEMISCH.get(gefunden, int(gefunden) if gefunden.isdigit() else 1)


def vereinskern(name: str) -> str:
    """
    The club name in comparable form - without the SG marker, punctuation and
    team number.

    Intended for comparison only, never for display. Numbers in the name are
    kept: "SV 09 Arnstadt" and "SV 1920 Arnstadt" would otherwise be the same
    club, and so would "FC Saalfeld" and "SG Saalfeld 46".
    """
    text = unicodedata.normalize("NFKD", name or "")
    text = text.replace("\u200b", "").replace("ß", "ss")
    text = text.encode("ascii", "ignore").decode().lower()

    # Remove the team number at the end - it is compared separately
    text = _NUMMER_AM_ENDE.sub(" ", text)

    woerter = re.sub(r"[^a-z0-9]+", " ", text).split()
    while woerter and woerter[0] in _SPIELGEMEINSCHAFT:
        woerter = woerter[1:]

    return " ".join(woerter)


# ===== Discovering divisions =====

# The slug of a division carries everything needed:
#   coffeecom-kreisoberliga-kreis-mittelthueringen-kreisoberliga-herren-saison2627-thueringen
#                                                  ^^^^^^^^^^^^^ ^^^^^^          ^^^^^^^^^^
#                                                  league level   team type      association
_SLUG = re.compile(
    r"/spieltagsuebersicht/"
    r"(?P<slug>[^/\"]*?-(?P<spielklasse>[a-z0-9]+)-(?P<art>herren|frauen|[a-g]-junior(?:en|innen))"
    r"(?:-ue\d+)?-saison(?P<saison>\d{4})-(?P<verband>[a-z-]+))"
    r"/-/staffel/(?P<id>[A-Z0-9-]+)"
)


def _staffeln_auf_seite(html: str, spielklasse: str, verband: str) -> List[Staffel]:
    """All divisions on a page that match the league level and association."""
    gefunden: Dict[str, Staffel] = {}

    for treffer in _SLUG.finditer(html):
        if treffer.group("art") != "herren":
            continue
        if treffer.group("spielklasse") != spielklasse or treffer.group("verband") != verband:
            continue

        staffel_id = treffer.group("id")
        if staffel_id in gefunden:
            continue

        pfad = f"/spieltagsuebersicht/{treffer.group('slug')}/-/staffel/{staffel_id}"
        gefunden[staffel_id] = Staffel(
            staffel_id=staffel_id,
            pfad=pfad,
            slug=treffer.group("slug"),
            spielklasse=spielklasse,
            verband=verband,
            anzeigename=_anzeigename(html, staffel_id) or treffer.group("slug"),
        )

    return list(gefunden.values())


def _anzeigename(html: str, staffel_id: str) -> Optional[str]:
    """The text of the link to this division, i.e. its readable name."""
    treffer = re.search(
        rf'staffel/{re.escape(staffel_id)}[^"]*"[^>]*>(.*?)</a>', html, re.S
    )
    if not treffer:
        return None

    name = " ".join(unescape(re.sub(r"<[^>]+>", " ", treffer.group(1))).split())

    return name or None


def _vereinsseite(suchbegriff: str) -> Optional[str]:
    """The first club page for a search term, as HTML."""
    treffer = re.findall(
        r'href="(https://www\.fussball\.de/verein/[^"]+)"',
        _hole(f"{BASIS_URL}/suche/-/text/{quote(suchbegriff)}"),
    )
    if not treffer:
        return None

    return _hole(treffer[0])


def entdecke_staffeln(ankerverein: str, spielklasse: str, verband: str = "thueringen",
                      mit_nachbarstaffeln: bool = True) -> List[Staffel]:
    """
    Finds the divisions of a league level, starting from a club that plays in
    it.

    The detour via a club is necessary because fussball.de offers no directory
    of competitions that could be scraped - the text search only finds clubs
    and persons. And it is the better way than fixed identifiers anyway: those
    change every season, a club does not.

    Self-checking: from the slug, the league level, team type *Herren* (men)
    and association must match. If the wrong club is found, no wrong division
    comes out as a result, but none at all.

    Multi-division leagues (Landesklasse 1 to 3) are complete with a single
    call: the division pages link to each other.

    mit_nachbarstaffeln=False stays with the division of the anchor club.
    Necessary for supra-regional leagues: from the Regionalliga Nordost the
    chain leads through all five Regionalligen, from the NOFV-Oberliga through
    all German Oberligen. But only the one in which the anchor really plays is
    needed.
    """
    seite = _vereinsseite(ankerverein)
    if not seite:
        logger.warning(f"Kein Verein zu '{ankerverein}' gefunden")
        return []

    staffeln = {s.staffel_id: s for s in _staffeln_auf_seite(seite, spielklasse, verband)}
    if not staffeln:
        logger.info(f"'{ankerverein}' spielt nicht in {spielklasse} ({verband})")
        return []

    # Multi-division leagues hang together as a chain: each division page
    # links the next one via rel="next", not all at once. So follow the chain
    # until it ends or closes.
    offen = list(staffeln.values()) if mit_nachbarstaffeln else []
    while offen:
        aktuell = offen.pop()
        try:
            seite = _hole(aktuell.url)
        except FussballDeNichtErreichbar as fehler:
            logger.warning(f"Staffel {aktuell.slug} nicht erreichbar: {fehler}")
            continue

        # In both directions: the page only links its direct neighbour, and the
        # starting club may be in the middle or last division. Anyone who only
        # follows rel="next" finds not a single further one from division 3.
        for richtung in re.findall(r'rel="(?:next|prev)"\s+href="([^"]+)"', seite):
            for nachbar in _staffeln_auf_seite(richtung, spielklasse, verband):
                if nachbar.staffel_id not in staffeln:
                    staffeln[nachbar.staffel_id] = nachbar
                    offen.append(nachbar)

    # Fill in display names where the link had no text (the next chain link
    # is an arrow icon without a label).
    staffeln = {sid: _mit_anzeigename(s) for sid, s in staffeln.items()}

    logger.info(f"{spielklasse} ({verband}): {len(staffeln)} Staffel(n) entdeckt")

    return sorted(staffeln.values(), key=lambda s: s.anzeigename)


def _mit_anzeigename(staffel: Staffel) -> Staffel:
    """
    Fetches the name of a division from its own page afterwards.

    Necessary for divisions found via the next chain: there the link is an
    arrow icon without text, and the slug as a substitute name would be
    unreadable in the user interface.
    """
    if staffel.anzeigename != staffel.slug:
        return staffel

    try:
        seite = _hole(staffel.url)
    except FussballDeNichtErreichbar:
        return staffel

    # The division page has no heading with its name. The link for saving it
    # as a favourite does carry it in full, though:
    #   text=26/27 - Herren - Landesklasse - Thüringen: Landesklasse Staffel 1
    # text= may be the first parameter, and & often appears in the HTML as &amp;
    treffer = re.search(r'my\.add\.favorite\?(?:[^"]*?&(?:amp;)?)?text=([^&"]+)', seite)
    if not treffer:
        return staffel

    beschriftung = unquote_plus(treffer.group(1))
    name = beschriftung.split(":", 1)[-1].strip()

    return replace(staffel, anzeigename=name or staffel.slug)


# ===== Reading the table =====

_TABELLENZEILE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_ZELLE = re.compile(r'<td([^>]*)>(.*?)</td>', re.S)
_TEAM_ID = re.compile(r"/mannschaft/[^\"]*?/team-id/([A-Z0-9]+)")


def hole_tabelle(staffel: Staffel) -> List[Tabellenplatz]:
    """
    Reads the table of a division.

    Returns an empty list if the page contains no table - cup rounds and
    tournaments have none, and a league before the first matchday sometimes
    does not have one yet either.
    """
    html = _hole(staffel.url)

    anfang = html.find("fixtures-league-table")
    if anfang < 0:
        logger.info(f"{staffel.anzeigename}: keine Tabelle auf der Seite")
        return []

    tabelle = []
    for zeile in _TABELLENZEILE.finditer(html[anfang:anfang + 300_000]):
        if platz := _zeile_auswerten(zeile.group(1)):
            tabelle.append(platz)

    logger.info(f"{staffel.anzeigename}: {len(tabelle)} Mannschaften")

    return tabelle


def _zeile_auswerten(zeile: str) -> Optional[Tabellenplatz]:
    """
    Builds a table position from a table row.

    Reading goes by the class names of the cells (column-rank, column-club,
    column-points) and not by their position: the number of columns varies
    with crest, trend arrow and hiding on narrow devices. The cells without
    their own class in between are matches played, wins, draws and losses; the
    goal difference is the only one with a colon.

    If a component is missing, the row is discarded. A half-read table row is
    worse than a missing one: an expense rate would later be derived from it.
    """
    zellen = [
        (treffer.group(1),
         " ".join(unescape(re.sub(r"<[^>]+>", " ", treffer.group(2))).replace("\u200b", "").split()))
        for treffer in _ZELLE.finditer(zeile)
    ]
    if not zellen:
        return None

    def zelle(klasse: str) -> Optional[str]:
        return next((text for attr, text in zellen if klasse in attr), None)

    rang = zelle("column-rank")
    name = zelle("column-club")
    punkte = zelle("column-points")
    if not rang or not name or not punkte:
        return None

    team_id = _TEAM_ID.search(zeile)
    torverhaeltnis = next(
        (re.fullmatch(r"(\d+)\s*:\s*(\d+)", text) for _, text in zellen
         if re.fullmatch(r"\d+\s*:\s*\d+", text)),
        None,
    )
    zahlen = [int(text) for attr, text in zellen
              if re.fullmatch(r"\d+", text) and "column-rank" not in attr and "column-points" not in attr]

    if not team_id or not torverhaeltnis or len(zahlen) < 4:
        return None

    try:
        platz = int(rang.rstrip("."))
        punktzahl = int(punkte)
    except ValueError:
        return None

    return Tabellenplatz(
        platz=platz,
        mannschaft=name,
        team_id=team_id.group(1),
        spiele=zahlen[0],
        siege=zahlen[1],
        unentschieden=zahlen[2],
        niederlagen=zahlen[3],
        tore=int(torverhaeltnis.group(1)),
        gegentore=int(torverhaeltnis.group(2)),
        punkte=punktzahl,
    )
