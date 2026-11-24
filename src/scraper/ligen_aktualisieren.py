"""
Nightly reconciliation of the league tables with fussball.de.

Which leagues are needed follows from the expense regulations (Spesenordnung):
for cup matches the highest-ranked participating team counts (§2 para. 3), for
friendlies the league level of the host (§2 para. 4). For that, all league
levels from Landesklasse upwards must be known - then a team that appears in
no table is necessarily below the Landesklasse and can no longer raise the
rate.

The division identifiers (Staffel-Kennungen) change every season and are
therefore not hard-coded anywhere. The starting point is a club that the
user's own assignments already know plays in the league in question - see
fussball_de.entdecke_staffeln.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

from db.database import get_connection
from db.ligen import ersetze_staffel
from scraper.fussball_de import FussballDeNichtErreichbar, entdecke_staffeln, hole_tabelle
from utils.logger import setup_logger

logger = setup_logger("ligen")


@dataclass(frozen=True)
class Ziel:
    """A league that is to be reconciled."""
    spielklasse: str          # as in the fussball.de slug
    verband: str              # as in the fussball.de slug
    dfbnet_spielklasse: str   # as DFBnet names it in the assignments
    mit_nachbarstaffeln: bool


ZIELE: Tuple[Ziel, ...] = (
    # Thuringian state level - multiple divisions, so follow the chain
    Ziel("verbandsliga", "thueringen", "Verbandsliga", True),
    Ziel("landesklasse", "thueringen", "Landesklasse", True),

    # Supra-regional. Not to derive rates from them, but to recognise THAT a
    # team plays supra-regionally - then the expenses stay empty.
    # Without neighbouring divisions: from the Regionalliga Nordost the chain
    # would otherwise lead through all five Regionalligen of Germany.
    Ziel("regionalliga", "region-nordostdeutschland", "Regionalliga Nordost", False),
    Ziel("oberliga", "deutschland", "Oberliga", False),
)

# How many clubs are tried per DFBnet division. The first anchor can miss - a
# club gets relegated, is renamed, or the text search does not find it.
ANKER_JE_STAFFEL = 3


def _ankervereine(dfbnet_spielklasse: str) -> List[str]:
    """
    Home teams from the user's own assignments in this league level.

    Home and not away, because the host provides the venue and thus certainly
    belongs to the organising association. Newest first: an assignment from
    the current season describes today's league, one that is three years old
    perhaps no longer does.

    Grouped by the division that DFBnet names, and served from those in turn.
    Otherwise, with parallel divisions, all anchors would come from the same
    one - the four most recent Oberliga assignments in this data set are all
    NOFV-Oberliga Nord, and the Sued division that matters for Thuringia would
    remain unknown.
    """
    conn = get_connection()

    try:
        zeilen = conn.execute(
            """
            SELECT staffel, heim_team, MAX(datum) AS letztes
            FROM matches
            WHERE mannschaftsart = 'Herren' AND spielklasse = ? AND heim_team != ''
            GROUP BY staffel, heim_team
            ORDER BY letztes DESC
            """,
            (dfbnet_spielklasse,),
        ).fetchall()
    finally:
        conn.close()

    je_staffel: Dict[str, List[str]] = {}
    for zeile in zeilen:
        gruppe = je_staffel.setdefault(zeile["staffel"] or "", [])
        if len(gruppe) < ANKER_JE_STAFFEL:
            gruppe.append(zeile["heim_team"])

    # In turn, so that each division gets its best anchor first
    anker: List[str] = []
    for runde in range(ANKER_JE_STAFFEL):
        for gruppe in je_staffel.values():
            if runde < len(gruppe):
                anker.append(gruppe[runde])

    return anker


def aktualisiere_liga(ziel: Ziel) -> int:
    """
    Reconciles one league. Returns the number of teams written.

    If the fetch fails, the existing data stays in place: an outdated table is
    usable, a half-emptied one is not.
    """
    anker = _ankervereine(ziel.dfbnet_spielklasse)
    if not anker:
        logger.info(
            f"{ziel.dfbnet_spielklasse}: keine eigene Ansetzung als Ausgangspunkt - "
            "diese Liga bleibt unbekannt"
        )
        return 0

    staffeln = {}
    for verein in anker:
        try:
            gefunden = entdecke_staffeln(
                verein, ziel.spielklasse, ziel.verband, ziel.mit_nachbarstaffeln
            )
        except FussballDeNichtErreichbar as fehler:
            logger.warning(f"{ziel.dfbnet_spielklasse} ({verein}): {fehler}")
            continue

        for staffel in gefunden:
            staffeln.setdefault(staffel.staffel_id, staffel)

        # A league with chained divisions is complete with the first hit - the
        # chain brought all its siblings along. Leagues without a chain, on the
        # other hand, run side by side (NOFV-Oberliga Nord and Sued), and each
        # starting club only knows its own. There all clubs must be tried,
        # otherwise exactly the division containing the Thuringian teams is
        # missing.
        if staffeln and ziel.mit_nachbarstaffeln:
            break

    if not staffeln:
        logger.warning(
            f"{ziel.dfbnet_spielklasse}: keiner der {len(anker)} Ausgangsvereine war zu finden"
        )
        return 0

    geschrieben = 0
    for staffel in staffeln.values():
        try:
            tabelle = hole_tabelle(staffel)
        except FussballDeNichtErreichbar as fehler:
            logger.warning(f"{staffel.anzeigename}: {fehler}")
            continue

        ersetze_staffel(staffel, tabelle)
        geschrieben += len(tabelle)

    logger.info(
        f"{ziel.dfbnet_spielklasse}: {len(staffeln)} Staffel(n), {geschrieben} Mannschaften"
    )

    return geschrieben


def aktualisiere_alle() -> int:
    """
    Reconciles all leagues. An error in one league does not stop the others.

    Returns:
        Total number of teams written.
    """
    logger.info("Ligatabellen werden abgeglichen")

    gesamt = 0
    for ziel in ZIELE:
        try:
            gesamt += aktualisiere_liga(ziel)
        except Exception as fehler:
            logger.error(f"{ziel.dfbnet_spielklasse}: {fehler}", exc_info=True)

    logger.info(f"Ligatabellen abgeglichen: {gesamt} Mannschaften")

    return gesamt
