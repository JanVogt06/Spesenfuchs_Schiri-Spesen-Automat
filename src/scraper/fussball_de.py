"""
Liga-Tabellen von fussball.de.

Gebraucht werden sie fuer zwei Dinge: den Reiter *Ligen* und die Spesen der
Pokal- und Freundschaftsspiele. Bei beiden richtet sich der Satz nicht nach
der Spielklasse des Spiels, sondern nach der der beteiligten Mannschaften
(§2 Abs. 3 und 4 der Spesenordnung), und die steht in den Ansetzungsdaten von
DFBnet nicht drin.

Die Seiten sind serverseitig gerendert und ohne Anmeldung lesbar, deshalb
genuegt urllib - wie beim Geocoder rechtfertigt das keine zusaetzliche
Abhaengigkeit. robots.txt von fussball.de erlaubt alles ausser /*-service/
und /tipply/.

Die Staffel-Kennungen sind NICHT fest verdrahtet: sie wechseln mit jeder
Saison. Stattdessen werden sie entdeckt (siehe entdecke_staffeln) - ausgehend
von einem Verein, von dem die eigenen Ansetzungen bereits wissen, dass er in
der gesuchten Liga spielt. Das ist selbstpruefend: der Slug einer Staffel
nennt Spielklasse, Mannschaftsart und Verband, es kann also nur die richtige
Staffel herauskommen oder gar keine.
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

# Mindestabstand zwischen zwei Anfragen. fussball.de nennt keine Zahl, aber
# ein naechtlicher Lauf ueber eine Handvoll Staffeln darf nicht wie ein
# Lastangriff aussehen.
MIN_INTERVALL = 1.0

_schloss = threading.Lock()
_letzte_anfrage = 0.0


class FussballDeNichtErreichbar(Exception):
    """Die Seite hat nicht geantwortet - anders als "nichts gefunden"."""


@dataclass(frozen=True)
class Staffel:
    """Eine Spielklasse-Staffel auf fussball.de."""
    staffel_id: str
    pfad: str            # vollstaendiger Pfad inkl. Slug, ohne Basis-URL
    slug: str
    spielklasse: str     # aus dem Slug, z.B. "verbandsliga"
    verband: str         # aus dem Slug, z.B. "thueringen"
    anzeigename: str     # z.B. "11Teamsports Thüringenliga"

    @property
    def url(self) -> str:
        return f"{BASIS_URL}{self.pfad}"


@dataclass(frozen=True)
class Tabellenplatz:
    """Eine Zeile einer Ligatabelle."""
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
    """Holt eine Seite, mit Mindestabstand zur vorherigen Anfrage."""
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


# ===== Namen vergleichbar machen =====

# Rechtsformen und Vereinskuerzel, die zwischen DFBnet und fussball.de
# wechseln koennen ("SG SV Alach I" gegen "SV Alach"). Die Nummer der
# Mannschaft gehoert ausdruecklich NICHT hierher - sie ist der Unterschied
# zwischen der ersten und der dritten Mannschaft und damit zwischen 50 und
# 25 Euro.
_KUERZEL = {
    "sg", "spg", "sv", "fsv", "tsv", "fc", "sc", "vfb", "vfl", "vfr", "spvgg",
    "bsg", "esv", "fsg", "tsg", "tus", "mtv", "bsv", "ssv", "svg", "lsv",
    "spielvereinigung", "sportfreunde", "spfd", "ev", "e", "v",
}

_NUMMER_ROEMISCH = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


def mannschaftsnummer(name: str) -> int:
    """
    Die Nummer der Mannschaft innerhalb ihres Vereins.

    DFBnet schreibt "SG SV Alach I", "FC Union Erfurt II" oder
    "SV 09 Arnstadt 2.", fussball.de "FC Empor Weimar 06 2.". Ohne Nummer ist
    die erste Mannschaft gemeint.

    Diese Zahl ist der wichtigste Teil des Vergleichs: die dritte Mannschaft
    des FC Saalfeld spielt Kreisliga, die erste Verbandsliga. Wer die Nummer
    wegwirft, verwechselt 25 Euro mit 50.
    """
    treffer = re.search(r"(?:^|[\s(])(i{1,3}|iv|[2-9])\s*\.?\s*$", (name or "").strip().lower())
    if not treffer:
        return 1

    gefunden = treffer.group(1)

    return _NUMMER_ROEMISCH.get(gefunden, int(gefunden) if gefunden.isdigit() else 1)


def vereinskern(name: str) -> str:
    """
    Der Vereinsname ohne Rechtsform, Zeichensetzung und Mannschaftsnummer.

    Nur zum Vergleichen gedacht, nie zum Anzeigen. Zahlen im Namen bleiben
    stehen: "SV 09 Arnstadt" und "SV 1920 Arnstadt" waeren sonst derselbe
    Verein.
    """
    text = unicodedata.normalize("NFKD", name or "")
    text = text.replace("​", "").replace("ß", "ss")
    text = text.encode("ascii", "ignore").decode().lower()

    # Mannschaftsnummer am Ende entfernen - sie wird getrennt verglichen
    text = re.sub(r"(?:^|[\s(])(?:i{1,3}|iv|[2-9])\s*\.?\s*$", " ", text)

    text = re.sub(r"[^a-z0-9]+", " ", text)
    woerter = [w for w in text.split() if w and w not in _KUERZEL]

    return " ".join(woerter)


# ===== Staffeln entdecken =====

# Der Slug einer Staffel traegt alles Noetige:
#   coffeecom-kreisoberliga-kreis-mittelthueringen-kreisoberliga-herren-saison2627-thueringen
#                                                  ^^^^^^^^^^^^^ ^^^^^^          ^^^^^^^^^^
#                                                  Spielklasse   Mannschaftsart  Verband
_SLUG = re.compile(
    r"/spieltagsuebersicht/"
    r"(?P<slug>[^/\"]*?-(?P<spielklasse>[a-z0-9]+)-(?P<art>herren|frauen|[a-g]-junior(?:en|innen))"
    r"(?:-ue\d+)?-saison(?P<saison>\d{4})-(?P<verband>[a-z-]+))"
    r"/-/staffel/(?P<id>[A-Z0-9-]+)"
)


def _staffeln_auf_seite(html: str, spielklasse: str, verband: str) -> List[Staffel]:
    """Alle Staffeln einer Seite, die zu Spielklasse und Verband passen."""
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
    """Der Text des Links auf diese Staffel, also ihr lesbarer Name."""
    treffer = re.search(
        rf'staffel/{re.escape(staffel_id)}[^"]*"[^>]*>(.*?)</a>', html, re.S
    )
    if not treffer:
        return None

    name = " ".join(unescape(re.sub(r"<[^>]+>", " ", treffer.group(1))).split())

    return name or None


def _vereinsseite(suchbegriff: str) -> Optional[str]:
    """Die erste Vereinsseite zu einem Suchbegriff, als HTML."""
    treffer = re.findall(
        r'href="(https://www\.fussball\.de/verein/[^"]+)"',
        _hole(f"{BASIS_URL}/suche/-/text/{quote(suchbegriff)}"),
    )
    if not treffer:
        return None

    return _hole(treffer[0])


def entdecke_staffeln(ankerverein: str, spielklasse: str, verband: str = "thueringen") -> List[Staffel]:
    """
    Sucht die Staffeln einer Spielklasse, ausgehend von einem Verein, der darin
    spielt.

    Der Umweg ueber einen Verein ist noetig, weil fussball.de kein Verzeichnis
    der Wettbewerbe anbietet, das sich abgreifen liesse - die Textsuche findet
    nur Vereine und Personen. Und er ist ohnehin der bessere Weg als feste
    Kennungen: die wechseln mit jeder Saison, ein Verein nicht.

    Selbstpruefend: aus dem Slug muessen Spielklasse, Mannschaftsart *Herren*
    und Verband stimmen. Wird der falsche Verein gefunden, kommt deshalb keine
    falsche Staffel heraus, sondern gar keine.

    Mehrstaffelige Ligen (Landesklasse 1 bis 3) sind mit einem Aufruf
    vollstaendig: die Staffelseiten verlinken einander.
    """
    seite = _vereinsseite(ankerverein)
    if not seite:
        logger.warning(f"Kein Verein zu '{ankerverein}' gefunden")
        return []

    staffeln = {s.staffel_id: s for s in _staffeln_auf_seite(seite, spielklasse, verband)}
    if not staffeln:
        logger.info(f"'{ankerverein}' spielt nicht in {spielklasse} ({verband})")
        return []

    # Mehrstaffelige Ligen haengen als Kette aneinander: jede Staffelseite
    # verlinkt per rel="next" die naechste, nicht alle auf einmal. Also der
    # Kette folgen, bis sie endet oder sich schliesst.
    offen = list(staffeln.values())
    while offen:
        aktuell = offen.pop()
        try:
            seite = _hole(aktuell.url)
        except FussballDeNichtErreichbar as fehler:
            logger.warning(f"Staffel {aktuell.slug} nicht erreichbar: {fehler}")
            continue

        naechste = re.search(r'rel="next"\s+href="([^"]+)"', seite)
        if not naechste:
            continue

        for nachbar in _staffeln_auf_seite(naechste.group(1), spielklasse, verband):
            if nachbar.staffel_id not in staffeln:
                staffeln[nachbar.staffel_id] = nachbar
                offen.append(nachbar)

    # Anzeigenamen nachtragen, wo der Link keinen Text hatte (die
    # next-Verkettung ist ein Pfeil-Icon ohne Beschriftung).
    staffeln = {sid: _mit_anzeigename(s) for sid, s in staffeln.items()}

    logger.info(f"{spielklasse} ({verband}): {len(staffeln)} Staffel(n) entdeckt")

    return sorted(staffeln.values(), key=lambda s: s.anzeigename)


def _mit_anzeigename(staffel: Staffel) -> Staffel:
    """
    Holt den Namen einer Staffel von ihrer eigenen Seite nach.

    Noetig fuer Staffeln, die ueber die next-Verkettung gefunden wurden: dort
    ist der Link ein Pfeil-Icon ohne Text, und der Slug als Ersatzname waere
    in der Oberflaeche unlesbar.
    """
    if staffel.anzeigename != staffel.slug:
        return staffel

    try:
        seite = _hole(staffel.url)
    except FussballDeNichtErreichbar:
        return staffel

    # Die Staffelseite hat keine Ueberschrift mit ihrem Namen. Der Link zum
    # Merken als Favorit traegt ihn aber vollstaendig mit:
    #   text=26/27 - Herren - Landesklasse - Thüringen: Landesklasse Staffel 1
    treffer = re.search(r'my\.add\.favorite\?[^"]*?[?&]text=([^&"]+)', seite)
    if not treffer:
        return staffel

    beschriftung = unquote_plus(treffer.group(1))
    name = beschriftung.split(":", 1)[-1].strip()

    return replace(staffel, anzeigename=name or staffel.slug)


# ===== Tabelle lesen =====

_TABELLENZEILE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_ZELLE = re.compile(r'<td([^>]*)>(.*?)</td>', re.S)
_TEAM_ID = re.compile(r"/mannschaft/[^\"]*?/team-id/([A-Z0-9]+)")


def hole_tabelle(staffel: Staffel) -> List[Tabellenplatz]:
    """
    Liest die Tabelle einer Staffel.

    Gibt eine leere Liste zurueck, wenn die Seite keine Tabelle enthaelt -
    Pokalrunden und Turniere haben keine, und eine Liga vor dem ersten
    Spieltag manchmal auch noch nicht.
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
    Baut aus einer Tabellenzeile einen Tabellenplatz.

    Gelesen wird ueber die Klassennamen der Zellen (column-rank, column-club,
    column-points) und nicht ueber ihre Position: die Zahl der Spalten
    schwankt mit Wappen, Trendpfeil und der Ausblendung auf schmalen Geraeten.
    Die Zellen ohne eigene Klasse dazwischen sind Spiele, Siege, Unentschieden
    und Niederlagen, das Torverhaeltnis ist die einzige mit Doppelpunkt.

    Fehlt ein Bestandteil, wird die Zeile verworfen. Eine halb gelesene
    Tabellenzeile ist schlimmer als eine fehlende: aus ihr wuerde spaeter ein
    Spesensatz.
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
