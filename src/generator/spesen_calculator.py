"""
Expense calculator (Spesen Calculator) - computes SR/SRA expenses per the TFV expense regulations (Spesenordnung)
(version of 01.07.2025), §2, and for the mandatory (Pflicht) matches of the NOFV Spielklassen (league levels)
per the NOFV finance regulations (Finanzordnung), §9 no. 7.

The calculator is the ONLY place that decides whether there is a rate
for a match. It used to apply only to league matches (Punktspiele), while callers had to
check separately whether a cup or friendly match was involved -
three places with the same rule, and the frozen rates in the
database were nevertheless those of a league match. Now it returns the right thing itself for
cup and friendly matches: a rate only where
it is independent of the Spielklasse of those involved, otherwise nothing.
"""
import re
from typing import Tuple, Optional

from utils.logger import setup_logger

logger = setup_logger("spesen_calculator")


# ===== EXPENSE TABLES per §2 para. 2 =====

# (2a) Men (Maenner) - league, deciding and qualification matches
SPESEN_MAENNER = {
    "verbandsliga": (50.00, 40.00),
    "landesklasse": (40.00, 30.00),
    "kreisoberliga": (30.00, 25.00),
    "kreisliga": (25.00, 23.00),
    "kreisklasse": (25.00, 23.00),
}

# (2a) Veterans (Alte Herren) - rows of their own in the same table. At district (Kreis) level there is
# only ONE rate ("Kreis Alte Herren"), regardless of whether the Staffel (division)
# is called Kreisoberliga, Kreisliga or Kreisklasse.
SPESEN_ALTE_HERREN_LANDESMEISTERSCHAFT = (40.00, 30.00)
SPESEN_ALTE_HERREN_KREIS = (25.00, 23.00)
SPESEN_ALTE_HERREN_KLEINFELD = (20.00, None)

# (2b) Women/Juniorinnen (girls)
SPESEN_FRAUEN = {
    "verbandsliga": (25.00, 20.00),
    "landesklasse": (25.00, 20.00),
    "kreisoberliga": (20.00, None),
}
SPESEN_JUNIORINNEN_DEFAULT = (20.00, None)  # "in allen Spiel- und Altersklassen" (in all match and age classes)

# (2c) Junioren (boys)
SPESEN_JUNIOREN_LANDESEBENE = (25.00, 20.00)  # A-, B-, C-Junioren
SPESEN_JUNIOREN_LANDESEBENE_DJUN = (20.00, None)  # D-Junioren, Talenteliga, small-pitch (Kleinfeld)
SPESEN_JUNIOREN_KREISEBENE_AB = (23.00, 18.00)  # A-, B-Junioren
SPESEN_JUNIOREN_KREISEBENE_JUNG = (20.00, 15.00)  # C-Junioren and younger

# The Spielklassen that the TFV runs at state (Landes) level. Deliberately a
# closed list instead of a catch-all branch: DFBnet normalizes the
# Spielklasse across association boundaries - a match of the HFV or FLB
# also appears there as "Landesliga" or "Verbandsliga", the association can
# only be recognized by the Staffel, which is not available here. A catch-all branch
# would silently give such matches the 25/20 of the TFV state level, although under
# §2 para. 6 the rates of the organizing association apply, which this regulation
# does not know. Better no rate and a note than a wrong amount.
SPIELKLASSEN_JUNIOREN_LANDESEBENE = (
    "verbandsliga",
    "landesklasse",
    "landesliga",
    "talenteliga",
    "kleinfeld",
    "fair-play-liga",
    "kinderfussball",
)


# Staffel names by which a match outside the TFV can be recognized.
# Necessary because DFBnet normalizes the Spielklasse across association boundaries:
# a league match in the Altmark appears there as "Kreisoberliga",
# an NOFV match of the C-Junioren as "Landesliga". Only the Staffel names the
# competition outright ("1. Altmark West Liga", "U14-Talente-Spielrunde-
# Nordost"). Under §2 para. 6 the organizing association pays there by its own
# flat rates, which this regulation does not know.
#
# Deliberately an exclusion list. An inclusion list is not possible: an
# ordinary Thuringian Staffel is simply called "Kreisliga Staffel 1" and
# names its association nowhere. The list can therefore never be complete -
# but it only ever takes rates away and never grants any, so a blind
# spot costs at most coverage, never correctness.
STAFFELN_FREMDER_VERBAND = (
    "nofv", "nordost", "dfb",
    "sachsen", "altmark", "hessen", "brandenburg", "bayern", "baden",
    "württemberg", "wuerttemberg", "niedersachsen", "westfalen", "pfalz",
    "saarland", "bremen", "hamburg", "holstein", "mecklenburg", "berlin",
    "mittelrhein", "niederrhein", "rheinland",
)

# The association abbreviations that appear in the short keys of friendly matches and
# tournaments for Thuringia ("FS/H/K-FS/MT/1" = Kreis Mittelthueringen,
# "FS/AJ/L-FS/TFV/1" = state association). Only here is the association structured
# enough for an inclusion list - everything else in this field is free text.
VERBANDSKUERZEL_TFV = ("tfv", "mt", "mth", "wt", "nt", "ot", "e-s", "jso", "ntkfa")

# (3a)/(4) Cup and friendly matches in the men's (Herren) category. The rate depends
# on the Spielklasse of the participating teams, not on that of the
# match; it is looked up in the nightly reconciled league tables
# (db.ligen).
#
# Deliberately only the two Thuringian Spielklassen. The rows of the regulation for
# 3. Liga, Regionalliga and Oberliga are missing here because supra-regional matches
# are not to be settled at all - the supra-regional tables serve
# solely to RECOGNIZE such a participation and then enter nothing.
# For friendly matches there is the added fact that the regulation names two rates
# side by side for the Regionalliga ("170 €/120 €"), without saying when which one
# applies.
SPESEN_HERREN_NACH_SPIELKLASSE = {
    "verbandsliga": (50.00, 40.00),
    "landesklasse": (40.00, 30.00),
}

PUNKTSPIEL = "punktspiel"
POKALSPIEL = "pokalspiel"
FREUNDSCHAFTSSPIEL = "freundschaftsspiel"


# ===== NOFV: Finanzordnung §9 no. 7 =====
#
# The TFV expense regulations do not apply to the NOFV Spielklassen, but rather the
# NOFV's finance regulations, and settlement is made on its own receipt -
# one page per referee instead of a shared one.
#
# Deliberately only the mandatory-match (Pflichtspiel) rates. "Sonstige Spiele" (other matches) depend in the
# Regionalliga on the Spielklasse of the opponent (no. 7.1 / 7.7), for
# women on the regulations of the state association (no. 7.3 / 7.9), and the Futsal
# Regionalliga (no. 7.6) names no rate for assistants. There it stays empty as
# before.
NOFV_HERREN_REGIONALLIGA = "herren-regionalliga"
NOFV_HERREN_OBERLIGA = "herren-oberliga"
NOFV_FRAUEN_REGIONALLIGA = "frauen-regionalliga"
NOFV_A_JUNIOREN_REGIONALLIGA = "a-junioren-regionalliga"
NOFV_BC_JUNIOREN_REGIONALLIGA = "bc-junioren-regionalliga"

SPESEN_NOFV = {
        NOFV_HERREN_REGIONALLIGA: (300.00, 150.00),      # no. 7.1 / 7.7
        NOFV_HERREN_OBERLIGA: (100.00, 60.00),           # no. 7.2 / 7.8
        NOFV_FRAUEN_REGIONALLIGA: (60.00, 40.00),        # no. 7.3 / 7.9
        NOFV_A_JUNIOREN_REGIONALLIGA: (50.00, 35.00),    # no. 7.4 / 7.10
        NOFV_BC_JUNIOREN_REGIONALLIGA: (40.00, 30.00),   # no. 7.5 / 7.11
}

# DFBnet keeps promotion matches (Aufstiegsspiele) and tournaments under the same Spielklasse as
# league play ("Regionalliga Nordost" / "Aufstiegsspiel zur NOFV-CJRL").
# Not regular mandatory matches of the Staffel - the teams there
# do not yet play Regionalliga at all.
STAFFELN_KEIN_NOFV_PFLICHTSPIEL = (
    "aufstieg", "relegation", "entscheidung", "qualifikation",
    "turnier", "futsal", "halle", "pokal", "freundschaft",
)


def nofv_spielklasse(spielklasse: str, mannschaftsart: str, staffel: str) -> Optional[str]:
    """
    Recognizes a mandatory match of an NOFV Spielklasse with a fixed rate.

    The only place for this decision: it determines the rate AND the
    form. Deliberately an inclusion list - a match that falls through here
    gets no rate and the TFV form, as before, whereas a wrongly recognized one
    would get an amount that nobody notices.

    The Oberliga needs "NOFV" in the Staffel: DFBnet also normalizes the
    Oberligen of other regional associations to the Spielklasse "Oberliga". For the
    Regionalliga the Spielklasse already names the association ("Regionalliga
    Nordost").

    Returns:
            Key into SPESEN_NOFV or None.
    """
    if wettbewerbsart(spielklasse) != PUNKTSPIEL:
        return None

    klasse = (spielklasse or "").lower().strip()
    art = (mannschaftsart or "").lower().strip()
    st = (staffel or "").lower()

    if any(wort in st or wort in klasse for wort in STAFFELN_KEIN_NOFV_PFLICHTSPIEL):
        return None

    if klasse == "oberliga":
        if art == "herren" and "nofv" in st and "oberliga" in st:
            return NOFV_HERREN_OBERLIGA
        return None

    if "regionalliga" not in klasse or "nordost" not in klasse or "regionalliga" not in st:
        return None

    # Exact comparison instead of substring: "Herren Ü35" is not a Regionalliga
    # team, and "A-Juniorinnen" must not pass as A-Junioren.
    if art == "herren":
        return NOFV_HERREN_REGIONALLIGA
    if art == "frauen":
        return NOFV_FRAUEN_REGIONALLIGA
    if art == "a-junioren":
        return NOFV_A_JUNIOREN_REGIONALLIGA
    if art in ("b-junioren", "c-junioren"):
        return NOFV_BC_JUNIOREN_REGIONALLIGA

    return None


def ist_nofv_spiel(spiel_info: dict) -> bool:
    """Whether the NOFV receipt rather than the TFV form applies to this match."""
    return nofv_spielklasse(
        spiel_info.get("spielklasse") or "",
        spiel_info.get("mannschaftsart") or "",
        spiel_info.get("staffel") or "",
    ) is not None


def wettbewerbsart(spielklasse: str) -> str:
    """
    Assigns a DFBnet Spielklasse to one of the three competition types.

    The only source for this distinction - it decides both the
    expense rate and which box on the form
    is ticked. Tournaments have no box of their own on the form and
    count with the rest as league matches; §2 para. 2 explicitly lists tournament series
    there.
    """
    s = (spielklasse or "").lower()

    if "pokal" in s:
        return POKALSPIEL
    if "freundschaft" in s:
        return FREUNDSCHAFTSSPIEL

    return PUNKTSPIEL


def calculate_spesen(spielklasse: str, mannschaftsart: str, staffel: str = "",
                     heim_team: str = "",
                     gast_team: str = "") -> Tuple[Optional[float], Optional[float]]:
    """
    Computes SR and SRA expenses per the TFV expense regulations.

    Args:
            spielklasse: Spielklasse from DFBnet (e.g. "Verbandsliga", "1.Kreisklasse")
            mannschaftsart: Team type (Mannschaftsart) from DFBnet (e.g. "Herren", "B-Junioren")
            staffel: Staffel from DFBnet (e.g. "1. Altmark West Liga"). Optional,
                    but without it matches of other state associations cannot be
                    recognized - see STAFFELN_FREMDER_VERBAND.
            heim_team, gast_team: The teams. Optional, but without them
                    cup and friendly matches in the men's category stay without a rate: there
                    the Spielklasse of the clubs decides.

    Returns:
            Tuple (sr_spesen, sra_spesen) - sra_spesen can be None if no SRA is provided
            For an unknown combination or non-TFV matches: (None, None)
    """
    if not spielklasse or not mannschaftsart:
        logger.warning("Spielklasse oder Mannschaftsart fehlt")
        return (None, None)

    spielklasse_lower = spielklasse.lower()
    mannschaftsart_lower = mannschaftsart.lower()

    # NOFV mandatory matches: NOFV finance regulations, §9 no. 7. Before the exclusion
    # of supra-regional matches, which leaves everything else above the TFV empty.
    nofv = nofv_spielklasse(spielklasse, mannschaftsart, staffel)
    if nofv:
        logger.debug(f"NOFV-Pflichtspiel {nofv}: {SPESEN_NOFV[nofv]}")
        return SPESEN_NOFV[nofv]

    # Exclude DFB/supra-regional matches (not TFV expense regulations)
    if _is_ueberregional(spielklasse_lower):
        logger.info(f"Überregionales Spiel (kein TFV): {spielklasse}")
        return (None, None)

    if _ist_fremder_verband(staffel):
        logger.info(f"Spiel eines anderen Verbandes, §2 Abs. 6: {staffel}")
        return (None, None)

    if wettbewerbsart(spielklasse) != PUNKTSPIEL:
        return _calc_pokal_oder_freundschaft(
            spielklasse_lower, mannschaftsart_lower, heim_team, gast_team
        )

    # Determine the category and call the corresponding calculation
    if _is_maenner(mannschaftsart_lower):
        return _calc_maenner(spielklasse_lower, mannschaftsart_lower)
    elif _is_frauen_oder_juniorinnen(mannschaftsart_lower):
        return _calc_frauen(spielklasse_lower, mannschaftsart_lower)
    elif _is_junioren(mannschaftsart_lower):
        return _calc_junioren(spielklasse_lower, mannschaftsart_lower)
    else:
        logger.warning(f"Unbekannte Mannschaftsart: {mannschaftsart}")
        return (None, None)


def _ist_fremder_verband(staffel: str) -> bool:
    """
    Checks whether the Staffel designates a match outside the TFV.

    Two ways, because the field has two forms: league Staffeln are
    free text ("1. Altmark West Liga") and are checked against keywords,
    friendly matches and tournaments carry a short key
    ("FS/H/K-FS/MT/1", "TU/H/VTUR/WT/1"), whose second-to-last field names the association
    or district and can therefore be checked against an inclusion list.
    """
    if not staffel:
        return False

    s = staffel.lower()

    if any(wort in s for wort in STAFFELN_FREMDER_VERBAND):
        return True

    schluessel = re.match(r"^(?:fs|tu)/[^/]+/[^/]+/([^/]+)/\d+$", s)

    return bool(schluessel) and schluessel.group(1) not in VERBANDSKUERZEL_TFV


def _is_ueberregional(spielklasse: str) -> bool:
    """Checks whether the match is supra-regional (DFB, Regionalliga, etc.)."""
    # Kreis Spielklassen are always local (e.g. Kreisoberliga ≠ Oberliga)
    if "kreis" in spielklasse:
        return False
    ueberregional_keywords = [
        "bundesliga",
        "regionalliga",
        "oberliga",
        "dfb",
        "nachwuchsliga",
    ]
    return any(keyword in spielklasse for keyword in ueberregional_keywords)


def _is_maenner(mannschaftsart: str) -> bool:
    """Checks whether men/veterans (Alte Herren)."""
    return any(x in mannschaftsart for x in ["herren", "männer"])


def is_alte_herren(mannschaftsart: str) -> bool:
    """
    Checks whether veterans (Alte Herren).

    DFBnet writes the Mannschaftsart as "Herren Ü32" to "Herren Ü50" -
    the words "Alte Herren" never appear there. A search for them would therefore
    always come up empty and every Ü match would pass as an ordinary men's match.
    """
    return "alte herren" in mannschaftsart or re.search(r"ü\s*\d{2}", mannschaftsart) is not None


def _is_frauen_oder_juniorinnen(mannschaftsart: str) -> bool:
    """Checks whether women or Juniorinnen."""
    return any(x in mannschaftsart for x in ["frauen", "damen", "juniorinnen", "mädchen"])


def _is_junioren(mannschaftsart: str) -> bool:
    """Checks whether male Junioren."""
    # "junioren" but NOT "juniorinnen"
    return "junioren" in mannschaftsart and "juniorinnen" not in mannschaftsart


def _is_kreisebene(spielklasse: str) -> bool:
    """Checks whether district (Kreis) level (not state level)."""
    return "kreis" in spielklasse


def _calc_maenner(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """Computes expenses for men/veterans per §2 para. 2a."""

    # Veterans have rows of their own and must not see the men's table:
    # a Kreisoberliga Ue45 would get the men's 30/25 there
    # instead of the veterans' 25/23.
    if is_alte_herren(mannschaftsart):
        return _calc_alte_herren(spielklasse)

    # Search the standard table
    for key, spesen in SPESEN_MAENNER.items():
        if key in spielklasse:
            logger.debug(f"Männer-Spesen gefunden: {key} -> SR {spesen[0]}€, SRA {spesen[1]}€")
            return spesen

    # Fallback: everything with "kreis" in the name -> Kreisliga/Kreisklasse rates
    if _is_kreisebene(spielklasse):
        logger.debug(f"Männer Kreisebene Fallback für: {spielklasse}")
        return SPESEN_MAENNER["kreisliga"]

    logger.warning(f"Keine Spesen gefunden für Männer: {spielklasse}")
    return (None, None)


def _calc_pokal_oder_freundschaft(spielklasse: str, mannschaftsart: str,
                                  heim_team: str, gast_team: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Computes expenses for cup and friendly matches per §2 para. 3 and 4.

    Both depend not on the Spielklasse of the match but on that
    of the participating teams: for the cup on the highest-ranked
    ("Die Entschaedigungssaetze richten sich nach der hoechstklassigen am Spiel
    beteiligten Mannschaft"), for the friendly on that of the host
    ("Entscheidend ist die aktuelle Spielklasse des Gastgebers"). The
    DFBnet assignment data says nothing of this - there the Spielklasse is
    "Kreispokal" or "Kreisfreundschaftsspiele", not the clubs' league.

    Three ways to a rate, in this order:

    1. Class-independent cases. Where the regulation knows only a single rate
          for a team type, there is nothing to look up.
    2. Men (Herren): look up in the league tables (see _calc_herren_nach_liga).
    3. Otherwise nothing. An empty field is filled in by the referee in the
          dressing room, a plausible-looking wrong amount goes
          unnoticed.
    """
    # Juniorinnen: 20 euros "in allen Spiel- und Altersklassen" (para. 2b). Para. 3
    # no. 2 and para. 4 both refer back to it, and since the row distinguishes no
    # class, there is nothing to look up.
    if "juniorinnen" in mannschaftsart or "mädchen" in mannschaftsart:
        logger.debug(f"Juniorinnen (klassenunabhängig): {SPESEN_JUNIORINNEN_DEFAULT}")
        return SPESEN_JUNIORINNEN_DEFAULT

    # Veterans at Kreis level: "Kreis Alte Herren" is a single row
    # for every Kreis Staffel. Whoever plays in the Kreispokal or
    # hosts a Kreis friendly match - the rate is the same.
    if is_alte_herren(mannschaftsart) and _is_kreisebene(spielklasse):
        if "kleinfeld" in spielklasse:
            return SPESEN_ALTE_HERREN_KLEINFELD

        logger.debug(f"Alte Herren Kreisebene (klassenunabhängig): {SPESEN_ALTE_HERREN_KREIS}")
        return SPESEN_ALTE_HERREN_KREIS

    if _is_maenner(mannschaftsart) and not is_alte_herren(mannschaftsart):
        return _calc_herren_nach_liga(spielklasse, heim_team, gast_team)

    logger.info(
        f"Kein klassenunabhängiger Satz für {spielklasse}/{mannschaftsart} - "
        "Pokal/Freundschaft richtet sich nach der Spielklasse der Vereine"
    )

    return (None, None)


def _calc_herren_nach_liga(spielklasse: str, heim_team: str,
                           gast_team: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Looks up the Spielklasse of the participating men's teams.

    The lookup is in the nightly reconciled league tables. They
    cover the Thuringian state level (Verbandsliga, Landesklasse) and
    additionally Regionalliga and Oberliga - the latter not to settle
    from, but to recognize a supra-regional participation.

    The rules, all cautious in the same direction:

    - Kreispokal: never a rate. All participants play at Kreis level, and there
        para. 2a distinguishes between Kreisoberliga (30/25) and Kreisliga
        (25/23) - which of the two, the assignment does not reveal.
    - If a team is supra-regional, it stays empty.
    - If a team appears in several tables, it cannot be said which
        applies - then it stays empty. It must not be treated like a team without a
        table, otherwise the opponent's rate would silently prevail, although it itself
        might play higher.
    - A team that appears in no table plays below the
        Landesklasse and cannot raise the rate. This conclusion holds, however,
        only as long as the supra-regional tables are present at all -
        otherwise it could just as well play Oberliga.
    - For a friendly match only the host counts, for the cup the
        higher of the two classes.
    """
    from db.ligen import suche_mannschaft, kennt_ueberregionale_ligen, RANG_UEBERREGIONAL

    if "pokal" in spielklasse and _is_kreisebene(spielklasse):
        logger.info("Kreispokal: Kreisoberliga oder Kreisliga nicht unterscheidbar")
        return (None, None)

    ist_pokal = "pokal" in spielklasse
    beteiligte = [heim_team, gast_team] if ist_pokal else [heim_team]
    if not all(beteiligte):
        return (None, None)

    gefunden = []
    for name in beteiligte:
        treffer = suche_mannschaft(name)

        if len(treffer) > 1:
            logger.info(f"{name} steht in mehreren Ligatabellen - Spielklasse nicht eindeutig")
            return (None, None)

        mannschaft = treffer[0] if treffer else None

        if mannschaft and mannschaft["rang"] <= RANG_UEBERREGIONAL:
            logger.info(
                f"{name} spielt {mannschaft['anzeigename']} - überregionale Beteiligung, "
                "kein Satz aus dieser Ordnung"
            )
            return (None, None)

        if mannschaft:
            gefunden.append(mannschaft)

    if not gefunden:
        logger.info(f"Keine der Mannschaften ({', '.join(beteiligte)}) steht in einer Ligatabelle")
        return (None, None)

    # "Appears in no table" means "below the Landesklasse" only
    # if everything above is covered.
    if len(gefunden) < len(beteiligte) and not kennt_ueberregionale_ligen():
        logger.info("Überregionale Tabellen fehlen - unbekannte Mannschaft nicht einzuordnen")
        return (None, None)

    hoechste = min(gefunden, key=lambda m: m["rang"])
    spesen = SPESEN_HERREN_NACH_SPIELKLASSE.get(hoechste["spielklasse"])

    if not spesen:
        logger.info(f"Kein Satz für Spielklasse {hoechste['spielklasse']}")
        return (None, None)

    logger.debug(f"Herren {spielklasse}: maßgeblich {hoechste['mannschaft']} "
                 f"({hoechste['anzeigename']}) -> {spesen}")

    return spesen


def _calc_alte_herren(spielklasse: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Computes expenses for veterans (Alte Herren) per §2 para. 2a.

    For veterans the table knows exactly three rows: Landesmeister-
    schaften (state championships), "Kreis Alte Herren" and "Kreis Kleinfeld Alte Herren". At
    Kreis level the same rate applies to every Staffel - a remuneration graded by Kreisoberliga
    and Kreisliga as for the men does not exist
    here.
    """
    if _is_kreisebene(spielklasse):
        if "kleinfeld" in spielklasse:
            logger.debug(f"Alte Herren Kreis Kleinfeld: {SPESEN_ALTE_HERREN_KLEINFELD}")
            return SPESEN_ALTE_HERREN_KLEINFELD

        logger.debug(f"Alte Herren Kreisebene: {SPESEN_ALTE_HERREN_KREIS}")
        return SPESEN_ALTE_HERREN_KREIS

    # The Ü competitions of the TFV at state level are the Landesmeisterschaften.
    # DFBnet lists them as Spielklasse "Landesturnier" or
    # "Hallen-Landesturnier"; the word "Landesmeisterschaft" appears only in the
    # Staffel, which is not available here.
    if "landesmeisterschaft" in spielklasse or "landesturnier" in spielklasse:
        logger.debug(f"Alte Herren Landesmeisterschaft: {SPESEN_ALTE_HERREN_LANDESMEISTERSCHAFT}")
        return SPESEN_ALTE_HERREN_LANDESMEISTERSCHAFT

    logger.warning(f"Keine Spesen gefunden für Alte Herren: {spielklasse}")
    return (None, None)


def _calc_frauen(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """Computes expenses for women/Juniorinnen per §2 para. 2b."""

    # Juniorinnen: always 20€, no SRA - "in allen Spiel- und Altersklassen"
    if "juniorinnen" in mannschaftsart or "mädchen" in mannschaftsart:
        logger.debug(f"Juniorinnen-Spesen: {SPESEN_JUNIORINNEN_DEFAULT}")
        return SPESEN_JUNIORINNEN_DEFAULT

    # Women: search the table
    for key, spesen in SPESEN_FRAUEN.items():
        if key in spielklasse:
            logger.debug(f"Frauen-Spesen gefunden: {key} -> SR {spesen[0]}€, SRA {spesen[1]}€")
            return spesen

    # Fallback Kreis level women
    if _is_kreisebene(spielklasse):
        logger.debug(f"Frauen Kreisebene Fallback für: {spielklasse}")
        return (20.00, None)

    logger.warning(f"Keine Spesen gefunden für Frauen: {spielklasse}")
    return (None, None)


def _calc_junioren(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """Computes expenses for Junioren (male) per §2 para. 2c."""

    # Determine the age group
    ist_d_junior_oder_juenger = any(
        x in mannschaftsart
        for x in ["d-junioren", "e-junioren", "f-junioren", "g-junioren"]
    )
    ist_c_junior_oder_juenger = ist_d_junior_oder_juenger or "c-junioren" in mannschaftsart

    # Kreis level
    if _is_kreisebene(spielklasse):
        if ist_c_junior_oder_juenger:
            # C-Junioren and younger: 20€ / 15€
            logger.debug(f"Junioren Kreisebene (C+jünger): {SPESEN_JUNIOREN_KREISEBENE_JUNG}")
            return SPESEN_JUNIOREN_KREISEBENE_JUNG
        else:
            # A-, B-Junioren: 23€ / 18€
            logger.debug(f"Junioren Kreisebene (A/B): {SPESEN_JUNIOREN_KREISEBENE_AB}")
            return SPESEN_JUNIOREN_KREISEBENE_AB

    # State level - only the Spielklassen of the TFV
    if not any(k in spielklasse for k in SPIELKLASSEN_JUNIOREN_LANDESEBENE):
        logger.warning(f"Keine Spesen gefunden für Junioren: {spielklasse}")
        return (None, None)

    if ist_d_junior_oder_juenger or "talenteliga" in spielklasse or "kleinfeld" in spielklasse:
        # D-Junioren, Talenteliga, small-pitch: 20€, no SRA
        logger.debug(f"Junioren Landesebene (D/Talenteliga/Kleinfeld): {SPESEN_JUNIOREN_LANDESEBENE_DJUN}")
        return SPESEN_JUNIOREN_LANDESEBENE_DJUN
    else:
        # A-, B-, C-Junioren state level: 25€ / 20€
        logger.debug(f"Junioren Landesebene (A/B/C): {SPESEN_JUNIOREN_LANDESEBENE}")
        return SPESEN_JUNIOREN_LANDESEBENE


def format_spesen(betrag: Optional[float]) -> str:
    """
    Formats the expense amount for display in the document.

    Args:
            betrag: Expense amount or None

    Returns:
            Formatted string (e.g. "25,00 €") or empty string
    """
    if betrag is None:
        return ""
    # German format: comma as decimal separator
    return f"{betrag:.2f} €".replace(".", ",")