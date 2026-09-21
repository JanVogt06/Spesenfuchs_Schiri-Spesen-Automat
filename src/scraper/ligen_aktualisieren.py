"""
Naechtlicher Abgleich der Ligatabellen mit fussball.de.

Welche Ligen gebraucht werden, ergibt sich aus der Spesenordnung: bei
Pokalspielen zaehlt die hoechstklassige beteiligte Mannschaft (§2 Abs. 3), bei
Freundschaftsspielen die Spielklasse des Gastgebers (§2 Abs. 4). Dafuer
muessen alle Spielklassen ab Landesklasse aufwaerts bekannt sein - dann ist
eine Mannschaft, die in keiner Tabelle steht, zwangslaeufig unterhalb der
Landesklasse und kann den Satz nicht mehr anheben.

Die Staffel-Kennungen wechseln mit jeder Saison und stehen deshalb nirgends
fest im Code. Als Ausgangspunkt dient ein Verein, von dem die eigenen
Ansetzungen bereits wissen, dass er in der gesuchten Liga spielt - siehe
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
    """Eine Liga, die abgeglichen werden soll."""
    spielklasse: str          # wie im Slug von fussball.de
    verband: str              # wie im Slug von fussball.de
    dfbnet_spielklasse: str   # wie DFBnet sie in den Ansetzungen nennt
    mit_nachbarstaffeln: bool


ZIELE: Tuple[Ziel, ...] = (
    # Thueringer Landesebene - mehrstaffelig, deshalb der Kette folgen
    Ziel("verbandsliga", "thueringen", "Verbandsliga", True),
    Ziel("landesklasse", "thueringen", "Landesklasse", True),

    # Ueberregional. Nicht um daraus Saetze zu bilden, sondern um zu erkennen,
    # DASS eine Mannschaft ueberregional spielt - dann bleiben die Spesen leer.
    # Ohne Nachbarstaffeln: von der Regionalliga Nordost fuehrt die Kette sonst
    # durch alle fuenf Regionalligen Deutschlands.
    Ziel("regionalliga", "region-nordostdeutschland", "Regionalliga Nordost", False),
    Ziel("oberliga", "deutschland", "Oberliga", False),
)

# Wieviele Vereine je DFBnet-Staffel probiert werden. Der erste Anker kann
# danebengehen - ein Verein steigt ab, wird umbenannt, oder die Textsuche
# findet ihn nicht.
ANKER_JE_STAFFEL = 3


def _ankervereine(dfbnet_spielklasse: str) -> List[str]:
    """
    Heimmannschaften aus den eigenen Ansetzungen dieser Spielklasse.

    Heim und nicht Gast, weil der Gastgeber die Spielstaette stellt und damit
    sicher zum ausrichtenden Verband gehoert. Neueste zuerst: eine Ansetzung
    aus der laufenden Saison beschreibt die heutige Liga, eine drei Jahre alte
    vielleicht nicht mehr.

    Gruppiert nach der Staffel, die DFBnet nennt, und reihum daraus bedient.
    Sonst kaemen bei parallelen Staffeln alle Anker aus derselben - die vier
    juengsten Oberliga-Ansetzungen dieses Bestandes sind saemtlich
    NOFV-Oberliga Nord, und die fuer Thueringen entscheidende Sued-Staffel
    bliebe unbekannt.
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

    # Reihum, damit jede Staffel mit ihrem besten Anker zuerst drankommt
    anker: List[str] = []
    for runde in range(ANKER_JE_STAFFEL):
        for gruppe in je_staffel.values():
            if runde < len(gruppe):
                anker.append(gruppe[runde])

    return anker


def aktualisiere_liga(ziel: Ziel) -> int:
    """
    Gleicht eine Liga ab. Gibt die Zahl der geschriebenen Mannschaften zurueck.

    Schlaegt der Abruf fehl, bleibt der bisherige Bestand stehen: eine
    veraltete Tabelle ist brauchbar, eine halb geleerte nicht.
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

        # Eine Liga mit verketteten Staffeln ist mit dem ersten Treffer
        # vollstaendig - die Kette hat alle Geschwister mitgebracht. Ligen ohne
        # Kette laufen dagegen nebeneinander (NOFV-Oberliga Nord und Sued), und
        # jeder Ausgangsverein kennt nur seine eigene. Dort muessen alle
        # Vereine durch, sonst fehlt genau die Staffel, in der die Thueringer
        # Mannschaften stehen.
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
    Gleicht alle Ligen ab. Ein Fehler in einer Liga stoppt die anderen nicht.

    Returns:
        Zahl der insgesamt geschriebenen Mannschaften.
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
