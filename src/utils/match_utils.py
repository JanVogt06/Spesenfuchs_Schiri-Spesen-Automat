"""
Match Utilities - Gemeinsame Funktionen für Match-Daten-Verarbeitung

Diese Funktionen werden von mehreren Modulen verwendet:
- main_api.py (API Endpoints)
- docx_generator.py (Dokument-Generierung)
- Weitere Module bei Bedarf
"""
import re
from typing import Tuple


def generate_filename_from_match(match: dict) -> str:
    """
    Generiert einen eindeutigen Dateinamen für ein Match-Dokument.

    WICHTIG: Diese Funktion ist die EINZIGE Quelle für Dateinamen-Generierung!
    Änderungen hier wirken sich auf alle Module aus.

    Args:
        match: Match-Dictionary mit spiel_info

    Returns:
        Dateiname im Format: Spesen_{heim}_vs_{gast}_{datum}.docx

    Example:
        >>> match = {'spiel_info': {'heim_team': 'FC Bayern', 'gast_team': 'BVB', 'anpfiff': 'Samstag · 08.11.2025 · 13:00 Uhr'}}
        >>> generate_filename_from_match(match)
        'Spesen_FC Bayern_vs_BVB_08-11-2025.docx'
    """
    spiel_info = match.get('spiel_info', {})
    heim = spiel_info.get('heim_team') or ''
    gast = spiel_info.get('gast_team') or ''
    anpfiff = spiel_info.get('anpfiff', '')

    # Extrahiere Datum im Format "08.11.2025"
    datum_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', anpfiff)
    if datum_match:
        datum_display = datum_match.group(1)
        datum_clean = datum_display.replace('.', '-')
    else:
        datum_clean = "01-01-2000"

    # Bereinige Team-Namen (Slash kann Probleme im Dateisystem machen)
    heim_clean = heim.replace('/', '-')
    gast_clean = gast.replace('/', '-')

    # Turnier-Ansetzungen haben keine Teams. Ohne die Anstosszeit hiessen alle
    # Turniere eines Tages gleich - im Sammel-ZIP landeten dann zwei Eintraege
    # unter demselben Namen.
    if not heim.strip() or not gast.strip():
        _, uhrzeit = parse_anpfiff(anpfiff)
        zeit_clean = uhrzeit.replace(':', '-') if uhrzeit else 'ohne-Zeit'
        return f"Spesen_Turnier_{datum_clean}_{zeit_clean}.docx"

    return f"Spesen_{heim_clean}_vs_{gast_clean}_{datum_clean}.docx"


def parse_anpfiff(anpfiff_str: str) -> Tuple[str, str]:
    """
    Parsed einen Anpfiff-String in Datum und Uhrzeit.

    Args:
        anpfiff_str: String im Format "Wochentag · DD.MM.YYYY · HH:MM Uhr"
                     z.B. "Samstag · 08.11.2025 · 13:00 Uhr"

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
    Extrahiert ISO-Datum aus Anpfiff-String für Sortierung/Vergleiche.

    Args:
        anpfiff: String im Format "Wochentag · DD.MM.YYYY · HH:MM Uhr"

    Returns:
        ISO-Datum im Format "YYYY-MM-DD" für korrekte Sortierung
        Bei Parsing-Fehler: "1900-01-01"

    Example:
        >>> extract_iso_date_from_anpfiff("Samstag · 08.11.2025 · 13:00 Uhr")
        '2025-11-08'
    """
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', anpfiff)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"

    return "1900-01-01"


def sanitize_team_name(team_name: str) -> str:
    """
    Bereinigt Team-Namen für Dateinamen und Anzeige.

    Entfernt/ersetzt Zeichen die in Dateisystemen problematisch sind.

    Args:
        team_name: Originaler Team-Name

    Returns:
        Bereinigter Team-Name
    """
    if not team_name:
        return "Unbekannt"

    # Zeichen die in Dateinamen problematisch sind
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

    return result.strip()