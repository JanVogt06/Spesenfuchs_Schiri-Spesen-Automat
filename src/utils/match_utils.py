"""
Match utilities - shared functions for match data processing

These functions are used by several modules:
- main_api.py (API endpoints)
- docx_generator.py (document generation)
- more modules as needed
"""
import re
from typing import Tuple

from generator.spesen_calculator import ist_nofv_spiel


def generate_filename_from_match(match: dict) -> str:
    """
    Generates a unique file name for a match document.

    IMPORTANT: This function is the ONLY source for file name generation!
    Changes here affect all modules.

    Args:
            match: Match dictionary with spiel_info

    Returns:
            File name in the format: Spesen_{heim}_vs_{gast}_{datum}.docx - for
            NOFV mandatory (Pflicht) matches with .xlsx, because their receipt is an Excel workbook
            with one sheet per referee.

    Example:
        >>> match = {'spiel_info': {'heim_team': 'FC Bayern', 'gast_team': 'BVB', 'anpfiff': 'Samstag · 08.11.2025 · 13:00 Uhr'}}
        >>> generate_filename_from_match(match)
        'Spesen_FC Bayern_vs_BVB_08-11-2025.docx'
    """
    spiel_info = match.get('spiel_info', {})
    heim = spiel_info.get('heim_team') or ''
    gast = spiel_info.get('gast_team') or ''
    # The column may be NULL - a None would make re.search crash
    anpfiff = spiel_info.get('anpfiff') or ''

    # Extract the date in the format "08.11.2025"
    datum_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', anpfiff)
    if datum_match:
        datum_display = datum_match.group(1)
        datum_clean = datum_display.replace('.', '-')
    else:
        datum_clean = "01-01-2000"

    # Clean up team names (slash can cause problems in the file system)
    heim_clean = heim.replace('/', '-')
    gast_clean = gast.replace('/', '-')

    # Tournament assignments have no teams. Without the kick-off time all
    # tournaments of one day would have the same name - in the bulk ZIP two entries would then
    # end up under the same name.
    endung = "xlsx" if ist_nofv_spiel(spiel_info) else "docx"

    if not heim.strip() or not gast.strip():
        _, uhrzeit = parse_anpfiff(anpfiff)
        zeit_clean = uhrzeit.replace(':', '-') if uhrzeit else 'ohne-Zeit'
        return f"Spesen_Turnier_{datum_clean}_{zeit_clean}.{endung}"

    return f"Spesen_{heim_clean}_vs_{gast_clean}_{datum_clean}.{endung}"


def parse_anpfiff(anpfiff_str: str) -> Tuple[str, str]:
    """
    Parses a kick-off (Anpfiff) string into date and time.

    Args:
            anpfiff_str: String in the format "weekday · DD.MM.YYYY · HH:MM Uhr"
                                      e.g. "Samstag · 08.11.2025 · 13:00 Uhr"

    Returns:
            Tuple (datum, uhrzeit)
        - datum: "08.11.2025"
        - uhrzeit: "13:00"

    Example:
        >>> parse_anpfiff("Samstag · 08.11.2025 · 13:00 Uhr")
        ('08.11.2025', '13:00')
    """
    try:
        parts = anpfiff_str.split('·')
        if len(parts) >= 3:
            datum = parts[1].strip()
            uhrzeit = parts[2].replace('Uhr', '').strip()
            return datum, uhrzeit
    except (AttributeError, IndexError):
        pass

    return anpfiff_str, ''


def extract_iso_date_from_anpfiff(anpfiff: str) -> str:
    """
    Extracts the ISO date from a kick-off string for sorting/comparison.

    Args:
            anpfiff: String in the format "weekday · DD.MM.YYYY · HH:MM Uhr"

    Returns:
            ISO date in the format "YYYY-MM-DD" for correct sorting
            On parsing error: "1900-01-01"

    Example:
        >>> extract_iso_date_from_anpfiff("Samstag · 08.11.2025 · 13:00 Uhr")
        '2025-11-08'
    """
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', anpfiff or '')
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"

    return "1900-01-01"


def sanitize_team_name(team_name: str) -> str:
    """
    Cleans up team names for file names and display.

    Removes/replaces characters that are problematic in file systems.

    Args:
            team_name: Original team name

    Returns:
            Cleaned team name
    """
    if not team_name:
        return "Unbekannt"

    # Characters that are problematic in file names
    replacements = {
        '/': '-',
        '\\': '-',
        ':': '-',
        '*': '',
        '?': '',
        '"': '',
        '<': '',
        '>': '',
        '|': '-',
    }

    result = team_name
    for old, new in replacements.items():
        result = result.replace(old, new)

    # If nothing remains after cleaning, the same applies as for empty
    return result.strip() or "Unbekannt"


def parse_saison_datum(text: str) -> Tuple[str, str]:
    """
    Parses the date column from the table of refereed matches.

    There the year is two-digit ("20.09.26, 15:00"), unlike in the
    kick-off string of the assignments ("... · 08.11.2025 · ..."). Hence a
    separate parser instead of extract_iso_date_from_anpfiff: its regular
    expression requires four digits and would find nothing here.

    Args:
            text: e.g. "20.09.26, 15:00"

    Returns:
            Tuple (iso_date, time), on parsing error ("1900-01-01", "")

    Example:
        >>> parse_saison_datum("20.09.26, 15:00")
        ('2026-09-20', '15:00')
    """
    treffer = re.search(r'(\d{2})\.(\d{2})\.(\d{2})(?!\d)', text or '')
    uhrzeit_treffer = re.search(r'(\d{1,2}:\d{2})', text or '')
    uhrzeit = uhrzeit_treffer.group(1) if uhrzeit_treffer else ''

    if not treffer:
        return "1900-01-01", uhrzeit

    tag, monat, jahr = treffer.groups()

    # DFBnet keeps the match table only for current and past seasons.
    # A two-digit year here is therefore always 20xx - the association does not offer
    # 1900 as an alternative.
    return f"20{jahr}-{monat}-{tag}", uhrzeit
