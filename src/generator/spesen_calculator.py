"""
Spesen Calculator - Berechnet SR/SRA-Spesen nach der TFV Spesenordnung
(Stand 01.07.2025), §2.

Der Rechner ist die EINZIGE Stelle, die entscheidet, ob es fuer ein Spiel
einen Satz gibt. Frueher galt er nur fuer Punktspiele, waehrend Aufrufer
getrennt pruefen mussten, ob ein Pokal- oder Freundschaftsspiel vorliegt -
drei Stellen mit derselben Regel, und die eingefrorenen Saetze in der
Datenbank waren trotzdem die eines Punktspiels. Jetzt liefert er fuer
Pokal- und Freundschaftsspiele selbst das Richtige: einen Satz nur dort, wo
er von der Spielklasse der Beteiligten unabhaengig ist, sonst nichts.
"""
import re
from typing import Tuple, Optional

from utils.logger import setup_logger

logger = setup_logger("spesen_calculator")


# ===== SPESEN-TABELLEN gemäß §2 Abs. 2 =====

# (2a) Männer - Punkt-, Entscheidungs- und Qualifikationsspiele
SPESEN_MAENNER = {
    "verbandsliga": (50.00, 40.00),
    "landesklasse": (40.00, 30.00),
    "kreisoberliga": (30.00, 25.00),
    "kreisliga": (25.00, 23.00),
    "kreisklasse": (25.00, 23.00),
}

# (2a) Alte Herren - eigene Zeilen derselben Tabelle. Auf Kreisebene gibt es
# nur EINEN Satz ("Kreis Alte Herren"), unabhaengig davon ob die Staffel
# Kreisoberliga, Kreisliga oder Kreisklasse heisst.
SPESEN_ALTE_HERREN_LANDESMEISTERSCHAFT = (40.00, 30.00)
SPESEN_ALTE_HERREN_KREIS = (25.00, 23.00)
SPESEN_ALTE_HERREN_KLEINFELD = (20.00, None)

# (2b) Frauen/Juniorinnen
SPESEN_FRAUEN = {
    "verbandsliga": (25.00, 20.00),
    "landesklasse": (25.00, 20.00),
    "kreisoberliga": (20.00, None),
}
SPESEN_JUNIORINNEN_DEFAULT = (20.00, None)  # "in allen Spiel- und Altersklassen"

# (2c) Junioren (männlich)
SPESEN_JUNIOREN_LANDESEBENE = (25.00, 20.00)  # A-, B-, C-Junioren
SPESEN_JUNIOREN_LANDESEBENE_DJUN = (20.00, None)  # D-Junioren, Talenteliga, Kleinfeld
SPESEN_JUNIOREN_KREISEBENE_AB = (23.00, 18.00)  # A-, B-Junioren
SPESEN_JUNIOREN_KREISEBENE_JUNG = (20.00, 15.00)  # C-Junioren und jünger

# Die Spielklassen, die der TFV auf Landesebene fuehrt. Bewusst eine
# geschlossene Liste statt eines Auffangzweigs: DFBnet normalisiert die
# Spielklasse ueber die Verbandsgrenze hinweg - ein Spiel des HFV oder FLB
# steht dort ebenfalls als "Landesliga" oder "Verbandsliga", der Verband ist
# nur an der Staffel zu erkennen, die hier nicht vorliegt. Ein Auffangzweig
# gaebe solchen Spielen still die 25/20 der TFV-Landesebene, obwohl nach
# §2 Abs. 6 die Saetze des ausrichtenden Verbandes gelten, die diese Ordnung
# nicht kennt. Lieber kein Satz und ein Hinweis als ein falscher Betrag.
SPIELKLASSEN_JUNIOREN_LANDESEBENE = (
    "verbandsliga",
    "landesklasse",
    "landesliga",
    "talenteliga",
    "kleinfeld",
    "fair-play-liga",
    "kinderfussball",
)


PUNKTSPIEL = "punktspiel"
POKALSPIEL = "pokalspiel"
FREUNDSCHAFTSSPIEL = "freundschaftsspiel"


def wettbewerbsart(spielklasse: str) -> str:
    """
    Ordnet eine DFBnet-Spielklasse einer der drei Wettbewerbsarten zu.

    Einzige Quelle fuer diese Unterscheidung - sie entscheidet sowohl ueber
    den Spesensatz als auch darueber, welches Kaestchen im Formular
    angekreuzt wird. Turniere haben im Formular kein eigenes Kaestchen und
    zaehlen wie der Rest zu den Punktspielen; §2 Abs. 2 fuehrt Turnierserien
    ausdruecklich dort mit auf.
    """
    s = (spielklasse or "").lower()

    if "pokal" in s:
        return POKALSPIEL
    if "freundschaft" in s:
        return FREUNDSCHAFTSSPIEL

    return PUNKTSPIEL


def calculate_spesen(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Berechnet SR- und SRA-Spesen gemäß TFV Spesenordnung.

    Args:
        spielklasse: Spielklasse aus DFBnet (z.B. "Verbandsliga", "1.Kreisklasse")
        mannschaftsart: Mannschaftsart aus DFBnet (z.B. "Herren", "B-Junioren")

    Returns:
        Tuple (sr_spesen, sra_spesen) - sra_spesen kann None sein wenn kein SRA vorgesehen
        Bei unbekannter Kombination oder Nicht-TFV-Spielen: (None, None)
    """
    if not spielklasse or not mannschaftsart:
        logger.warning("Spielklasse oder Mannschaftsart fehlt")
        return (None, None)

    spielklasse_lower = spielklasse.lower()
    mannschaftsart_lower = mannschaftsart.lower()

    # DFB/Überregionale Spiele ausschließen (nicht TFV-Spesenordnung)
    if _is_ueberregional(spielklasse_lower):
        logger.info(f"Überregionales Spiel (kein TFV): {spielklasse}")
        return (None, None)

    if wettbewerbsart(spielklasse) != PUNKTSPIEL:
        return _calc_pokal_oder_freundschaft(spielklasse_lower, mannschaftsart_lower)

    # Kategorie bestimmen und entsprechende Berechnung aufrufen
    if _is_maenner(mannschaftsart_lower):
        return _calc_maenner(spielklasse_lower, mannschaftsart_lower)
    elif _is_frauen_oder_juniorinnen(mannschaftsart_lower):
        return _calc_frauen(spielklasse_lower, mannschaftsart_lower)
    elif _is_junioren(mannschaftsart_lower):
        return _calc_junioren(spielklasse_lower, mannschaftsart_lower)
    else:
        logger.warning(f"Unbekannte Mannschaftsart: {mannschaftsart}")
        return (None, None)


def _is_ueberregional(spielklasse: str) -> bool:
    """Prüft ob Spiel überregional ist (DFB, Regionalliga, etc.)."""
    # Kreis-Spielklassen sind immer lokal (z.B. Kreisoberliga ≠ Oberliga)
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
    """Prüft ob Männer/Alte Herren."""
    return any(x in mannschaftsart for x in ["herren", "männer"])


def is_alte_herren(mannschaftsart: str) -> bool:
    """
    Prüft ob Alte Herren.

    DFBnet schreibt die Mannschaftsart als "Herren Ü32" bis "Herren Ü50" -
    das Wort "Alte Herren" steht dort nie. Eine Suche danach ginge deshalb
    immer ins Leere und jedes Ü-Spiel liefe als normales Männerspiel durch.
    """
    return "alte herren" in mannschaftsart or re.search(r"ü\s*\d{2}", mannschaftsart) is not None


def _is_frauen_oder_juniorinnen(mannschaftsart: str) -> bool:
    """Prüft ob Frauen oder Juniorinnen."""
    return any(x in mannschaftsart for x in ["frauen", "damen", "juniorinnen", "mädchen"])


def _is_junioren(mannschaftsart: str) -> bool:
    """Prüft ob männliche Junioren."""
    # "junioren" aber NICHT "juniorinnen"
    return "junioren" in mannschaftsart and "juniorinnen" not in mannschaftsart


def _is_kreisebene(spielklasse: str) -> bool:
    """Prüft ob Kreisebene (nicht Landesebene)."""
    return "kreis" in spielklasse


def _calc_maenner(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """Berechnet Spesen für Männer/Alte Herren gemäß §2 Abs. 2a."""

    # Alte Herren haben eigene Zeilen und duerfen die Maenner-Tabelle nicht
    # sehen: eine Kreisoberliga Ue45 bekaeme dort die 30/25 der Maenner
    # statt der 25/23 der Alten Herren.
    if is_alte_herren(mannschaftsart):
        return _calc_alte_herren(spielklasse)

    # Standard-Tabelle durchsuchen
    for key, spesen in SPESEN_MAENNER.items():
        if key in spielklasse:
            logger.debug(f"Männer-Spesen gefunden: {key} -> SR {spesen[0]}€, SRA {spesen[1]}€")
            return spesen

    # Fallback: Alles mit "kreis" im Namen -> Kreisliga/Kreisklasse Sätze
    if _is_kreisebene(spielklasse):
        logger.debug(f"Männer Kreisebene Fallback für: {spielklasse}")
        return SPESEN_MAENNER["kreisliga"]

    logger.warning(f"Keine Spesen gefunden für Männer: {spielklasse}")
    return (None, None)


def _calc_pokal_oder_freundschaft(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Berechnet Spesen für Pokal- und Freundschaftsspiele gemäß §2 Abs. 3 und 4.

    Beide richten sich nicht nach der Spielklasse des Spiels, sondern nach der
    der beteiligten Mannschaften: beim Pokal nach der hoechstklassigen
    ("Die Entschaedigungssaetze richten sich nach der hoechstklassigen am Spiel
    beteiligten Mannschaft"), beim Freundschaftsspiel nach der des Gastgebers
    ("Entscheidend ist die aktuelle Spielklasse des Gastgebers"). Beides steht
    in den Ansetzungsdaten von DFBnet nicht drin - dort ist die Spielklasse
    "Kreispokal" oder "Kreisfreundschaftsspiele", nicht die Liga der Vereine.

    Deshalb wird hier nur gerechnet, wo das Ergebnis von der Spielklasse der
    Beteiligten gar nicht abhaengen KANN, weil die Ordnung fuer die
    Mannschaftsart ohnehin nur einen einzigen Satz kennt. Alles andere bleibt
    leer: ein leeres Feld traegt der Schiedsrichter in der Kabine selbst nach,
    ein plausibel aussehender falscher Betrag faellt niemandem auf.

    Die vollstaendige Abdeckung braucht die aktuelle Spielklasse der Vereine
    aus einer anderen Quelle; bis dahin ist Schweigen die richtige Antwort.
    """
    # Juniorinnen: 20 Euro "in allen Spiel- und Altersklassen" (Abs. 2b). Abs. 3
    # Nr. 2 und Abs. 4 verweisen beide dorthin zurueck, und da die Zeile keine
    # Klasse unterscheidet, gibt es nichts nachzuschlagen.
    if "juniorinnen" in mannschaftsart or "mädchen" in mannschaftsart:
        logger.debug(f"Juniorinnen (klassenunabhängig): {SPESEN_JUNIORINNEN_DEFAULT}")
        return SPESEN_JUNIORINNEN_DEFAULT

    # Alte Herren auf Kreisebene: "Kreis Alte Herren" ist eine einzige Zeile
    # fuer jede Kreisstaffel. Wer auch immer im Kreispokal antritt oder
    # Gastgeber eines Kreisfreundschaftsspiels ist - der Satz ist derselbe.
    if is_alte_herren(mannschaftsart) and _is_kreisebene(spielklasse):
        if "kleinfeld" in spielklasse:
            return SPESEN_ALTE_HERREN_KLEINFELD

        logger.debug(f"Alte Herren Kreisebene (klassenunabhängig): {SPESEN_ALTE_HERREN_KREIS}")
        return SPESEN_ALTE_HERREN_KREIS

    logger.info(
        f"Kein klassenunabhängiger Satz für {spielklasse}/{mannschaftsart} - "
        "Pokal/Freundschaft richtet sich nach der Spielklasse der Vereine"
    )
    return (None, None)


def _calc_alte_herren(spielklasse: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Berechnet Spesen für Alte Herren gemäß §2 Abs. 2a.

    Die Tabelle kennt fuer Alte Herren genau drei Zeilen: Landesmeister-
    schaften, "Kreis Alte Herren" und "Kreis Kleinfeld Alte Herren". Auf
    Kreisebene gilt derselbe Satz fuer jede Staffel - eine nach Kreisoberliga
    und Kreisliga gestaffelte Verguetung wie bei den Maennern gibt es hier
    nicht.
    """
    if _is_kreisebene(spielklasse):
        if "kleinfeld" in spielklasse:
            logger.debug(f"Alte Herren Kreis Kleinfeld: {SPESEN_ALTE_HERREN_KLEINFELD}")
            return SPESEN_ALTE_HERREN_KLEINFELD

        logger.debug(f"Alte Herren Kreisebene: {SPESEN_ALTE_HERREN_KREIS}")
        return SPESEN_ALTE_HERREN_KREIS

    # Die Ue-Wettbewerbe des TFV auf Landesebene sind die Landesmeisterschaften.
    # DFBnet fuehrt sie als Spielklasse "Landesturnier" bzw.
    # "Hallen-Landesturnier"; das Wort "Landesmeisterschaft" steht nur in der
    # Staffel, die hier nicht vorliegt.
    if "landesmeisterschaft" in spielklasse or "landesturnier" in spielklasse:
        logger.debug(f"Alte Herren Landesmeisterschaft: {SPESEN_ALTE_HERREN_LANDESMEISTERSCHAFT}")
        return SPESEN_ALTE_HERREN_LANDESMEISTERSCHAFT

    logger.warning(f"Keine Spesen gefunden für Alte Herren: {spielklasse}")
    return (None, None)


def _calc_frauen(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """Berechnet Spesen für Frauen/Juniorinnen gemäß §2 Abs. 2b."""

    # Juniorinnen: immer 20€, kein SRA - "in allen Spiel- und Altersklassen"
    if "juniorinnen" in mannschaftsart or "mädchen" in mannschaftsart:
        logger.debug(f"Juniorinnen-Spesen: {SPESEN_JUNIORINNEN_DEFAULT}")
        return SPESEN_JUNIORINNEN_DEFAULT

    # Frauen: Tabelle durchsuchen
    for key, spesen in SPESEN_FRAUEN.items():
        if key in spielklasse:
            logger.debug(f"Frauen-Spesen gefunden: {key} -> SR {spesen[0]}€, SRA {spesen[1]}€")
            return spesen

    # Fallback Kreisebene Frauen
    if _is_kreisebene(spielklasse):
        logger.debug(f"Frauen Kreisebene Fallback für: {spielklasse}")
        return (20.00, None)

    logger.warning(f"Keine Spesen gefunden für Frauen: {spielklasse}")
    return (None, None)


def _calc_junioren(spielklasse: str, mannschaftsart: str) -> Tuple[Optional[float], Optional[float]]:
    """Berechnet Spesen für Junioren (männlich) gemäß §2 Abs. 2c."""

    # Altersklasse bestimmen
    ist_d_junior_oder_juenger = any(
        x in mannschaftsart
        for x in ["d-junioren", "e-junioren", "f-junioren", "g-junioren"]
    )
    ist_c_junior_oder_juenger = ist_d_junior_oder_juenger or "c-junioren" in mannschaftsart

    # Kreisebene
    if _is_kreisebene(spielklasse):
        if ist_c_junior_oder_juenger:
            # C-Junioren und jünger: 20€ / 15€
            logger.debug(f"Junioren Kreisebene (C+jünger): {SPESEN_JUNIOREN_KREISEBENE_JUNG}")
            return SPESEN_JUNIOREN_KREISEBENE_JUNG
        else:
            # A-, B-Junioren: 23€ / 18€
            logger.debug(f"Junioren Kreisebene (A/B): {SPESEN_JUNIOREN_KREISEBENE_AB}")
            return SPESEN_JUNIOREN_KREISEBENE_AB

    # Landesebene - nur die Spielklassen des TFV
    if not any(k in spielklasse for k in SPIELKLASSEN_JUNIOREN_LANDESEBENE):
        logger.warning(f"Keine Spesen gefunden für Junioren: {spielklasse}")
        return (None, None)

    if ist_d_junior_oder_juenger or "talenteliga" in spielklasse or "kleinfeld" in spielklasse:
        # D-Junioren, Talenteliga, Kleinfeld: 20€, kein SRA
        logger.debug(f"Junioren Landesebene (D/Talenteliga/Kleinfeld): {SPESEN_JUNIOREN_LANDESEBENE_DJUN}")
        return SPESEN_JUNIOREN_LANDESEBENE_DJUN
    else:
        # A-, B-, C-Junioren Landesebene: 25€ / 20€
        logger.debug(f"Junioren Landesebene (A/B/C): {SPESEN_JUNIOREN_LANDESEBENE}")
        return SPESEN_JUNIOREN_LANDESEBENE


def format_spesen(betrag: Optional[float]) -> str:
    """
    Formatiert Spesen-Betrag für Anzeige im Dokument.

    Args:
        betrag: Spesen-Betrag oder None

    Returns:
        Formatierter String (z.B. "25,00 €") oder leerer String
    """
    if betrag is None:
        return ""
    # Deutsches Format: Komma als Dezimaltrenner
    return f"{betrag:.2f} €".replace(".", ",")