"""
DOCX generator - fills the expense settlement (Spesenabrechnung) template with data
Improved version with correct checkbox formatting
"""
from io import BytesIO
from pathlib import Path
from typing import Optional
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from utils.logger import setup_logger
from utils.match_utils import parse_anpfiff, generate_filename_from_match, sanitize_team_name, extract_iso_date_from_anpfiff
from generator.spesen_calculator import (
    FREUNDSCHAFTSSPIEL,
    POKALSPIEL,
    calculate_spesen,
    format_spesen,
    is_alte_herren,
    wettbewerbsart,
)

logger = setup_logger("docx_generator")

# Mileage allowance per the form
KM_SATZ_EURO = 0.30

# Checkbox characters (both Unicode, both renderable with Segoe UI Symbol)
CHECKBOX_CHECKED = '☒'    # U+2612 - Ballot Box with X
CHECKBOX_UNCHECKED = '☐'  # U+2610 - Ballot Box (empty)
CHECKBOX_FONT = 'Segoe UI Symbol'


def format_name_nachname_vorname(name: str) -> str:
    """
    Converts a scraped name in the format "Vorname Nachname" (first name last name) into the format
    "Nachname, Vorname" (last name, first name) expected on the form.
    The last word counts as the last name, the rest as the first name.
    """
    parts = name.strip().split()
    if len(parts) < 2:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


class SpesenGenerator:
    """Generates filled-in expense settlement documents"""

    def __init__(self, template_path: str, output_dir: Optional[Path] = None):
        """
        Initializes the generator.

        Args:
                template_path: Path to the DOCX template
                output_dir: Optional - only needed if documents are to be
                                        written to disk. For the download path
                                        it stays None and render_document() returns bytes.
        """
        self.template_path = Path(template_path)
        self.output_dir = Path(output_dir) if output_dir else None

        if self.output_dir:
            self.output_dir.mkdir(exist_ok=True, parents=True)

        if not self.template_path.exists():
            raise FileNotFoundError(f"Vorlage nicht gefunden: {self.template_path}")

        logger.debug(f"Generator initialisiert mit Vorlage: {self.template_path}")

    def _determine_checkboxes(self, match_data: dict) -> dict:
        """Determines which checkboxes have to be ticked."""
        spiel_info = match_data.get('spiel_info', {})

        checkbox_keys = [
            'CHECKBOX_PUNKTSPIEL', 'CHECKBOX_POKALSPIEL', 'CHECKBOX_ENTSCHEIDUNG',
            'CHECKBOX_FREUNDSCHAFT', 'CHECKBOX_MAENNER', 'CHECKBOX_FRAUEN',
            'CHECKBOX_MAEDCHEN', 'CHECKBOX_ALTE_HERREN', 'CHECKBOX_SONSTIGE',
            'CHECKBOX_A_JUN', 'CHECKBOX_B_JUN', 'CHECKBOX_C_JUN',
            'CHECKBOX_D_JUN', 'CHECKBOX_E_JUN', 'CHECKBOX_F_JUN',
        ]
        checkboxes = {key: False for key in checkbox_keys}

        # Check the Spielklasse (league level)
        art = wettbewerbsart(spiel_info.get('spielklasse', ''))
        if art == POKALSPIEL:
            checkboxes['CHECKBOX_POKALSPIEL'] = True
        elif art == FREUNDSCHAFTSSPIEL:
            checkboxes['CHECKBOX_FREUNDSCHAFT'] = True
        else:
            checkboxes['CHECKBOX_PUNKTSPIEL'] = True

        # Check the team type (Mannschaftsart). The order matters: Juniorinnen (girls' teams) must come before
        # the Junioren (boys') branches of the same name, otherwise a
        # girls' match ends up in the wrong row depending on the spelling.
        mannschaftsart = spiel_info.get('mannschaftsart', '').lower()
        if 'juniorinnen' in mannschaftsart or 'mädchen' in mannschaftsart:
            # The form has only the row "Maedchen" (girls) for Juniorinnen -
            # the age groups below it are the boys' ones.
            checkboxes['CHECKBOX_MAEDCHEN'] = True
        elif 'herren' in mannschaftsart or 'männer' in mannschaftsart:
            if is_alte_herren(mannschaftsart):
                checkboxes['CHECKBOX_ALTE_HERREN'] = True
            else:
                checkboxes['CHECKBOX_MAENNER'] = True
        elif 'frauen' in mannschaftsart:
            checkboxes['CHECKBOX_FRAUEN'] = True
        elif 'a-junioren' in mannschaftsart:
            checkboxes['CHECKBOX_A_JUN'] = True
        elif 'b-junioren' in mannschaftsart:
            checkboxes['CHECKBOX_B_JUN'] = True
        elif 'c-junioren' in mannschaftsart:
            checkboxes['CHECKBOX_C_JUN'] = True
        elif 'd-junioren' in mannschaftsart:
            checkboxes['CHECKBOX_D_JUN'] = True
        elif 'e-junioren' in mannschaftsart:
            checkboxes['CHECKBOX_E_JUN'] = True
        elif 'f-junioren' in mannschaftsart:
            checkboxes['CHECKBOX_F_JUN'] = True
        else:
            checkboxes['CHECKBOX_SONSTIGE'] = True

        return checkboxes

    def _get_referee_by_role(self, referees: list, role: str) -> dict:
        """Finds referees by role."""
        for ref in referees:
            if ref.get('rolle') == role:
                return ref
        return {}

    def _set_run_font(self, run, font_name: str):
        """Sets the font of a run completely."""
        run.font.name = font_name
        r = run._element
        rPr = r.get_or_add_rPr()
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            rFonts = OxmlElement('w:rFonts')
            rPr.insert(0, rFonts)
        rFonts.set(qn('w:ascii'), font_name)
        rFonts.set(qn('w:hAnsi'), font_name)
        rFonts.set(qn('w:cs'), font_name)
        rFonts.set(qn('w:eastAsia'), font_name)

    @staticmethod
    def _collect_replacements(checkbox_states: dict, text_replacements: dict) -> dict:
        """Builds the table placeholder -> (replacement text, is checkbox)."""
        all_replacements = {}

        for key, is_checked in checkbox_states.items():
            placeholder = f"{{{{{key}}}}}"
            char = CHECKBOX_CHECKED if is_checked else CHECKBOX_UNCHECKED
            all_replacements[placeholder] = (char, True)  # True = is a checkbox

        for key, value in text_replacements.items():
            placeholder = f"{{{{{key}}}}}"
            all_replacements[placeholder] = (str(value), False)  # False = is text

        return all_replacements

    def _replace_in_paragraph(self, paragraph, all_replacements: dict):
        """
        Replaces placeholders in a paragraph.
        Also handles placeholders that are spread over several runs.

        The paragraph text is assembled once and used as a filter: the
        vast majority of the template's paragraphs contain no placeholder at all,
        and re-assembling the text from the runs for each placeholder was by far the
        most expensive part of the generation.
        """
        runs = paragraph.runs
        if not runs:
            return

        full_text = ''.join(run.text for run in runs)
        if '{{' not in full_text:
            return

        # Only touch the placeholders that actually occur here. The
        # text can go stale through a replacement, but replacement values never
        # bring new placeholders with them - one hit too many is harmless, because
        # _replace_placeholder_in_paragraph checks again itself.
        for placeholder, (replacement, is_checkbox) in all_replacements.items():
            if placeholder in full_text:
                self._replace_placeholder_in_paragraph(paragraph, placeholder, replacement, is_checkbox)

    def _replace_placeholder_in_paragraph(self, paragraph, placeholder: str, replacement: str, is_checkbox: bool):
        """
        Replaces a placeholder in a paragraph - even if it is spread over several runs.
        """
        runs = paragraph.runs
        if not runs:
            return

        # Determine the full text and run boundaries
        full_text = ''.join(run.text for run in runs)

        if placeholder not in full_text:
            return

        # Find the position of the placeholder
        start_idx = full_text.find(placeholder)
        end_idx = start_idx + len(placeholder)

        # Find which runs are affected
        char_count = 0
        start_run_idx = None
        end_run_idx = None
        start_char_in_run = None
        end_char_in_run = None

        for i, run in enumerate(runs):
            run_start = char_count
            run_end = char_count + len(run.text)

            # Start of the placeholder in this run?
            if start_run_idx is None and run_start <= start_idx < run_end:
                start_run_idx = i
                start_char_in_run = start_idx - run_start

            # End of the placeholder in this run?
            if end_run_idx is None and run_start < end_idx <= run_end:
                end_run_idx = i
                end_char_in_run = end_idx - run_start

            char_count = run_end

        if start_run_idx is None or end_run_idx is None:
            return

        # Case 1: placeholder entirely within one run
        if start_run_idx == end_run_idx:
            run = runs[start_run_idx]
            run.text = run.text[:start_char_in_run] + replacement + run.text[end_char_in_run:]
            if is_checkbox:
                self._set_run_font(run, CHECKBOX_FONT)

        # Case 2: placeholder spread over several runs
        else:
            # First run: text before the placeholder + replacement
            first_run = runs[start_run_idx]
            first_run.text = first_run.text[:start_char_in_run] + replacement
            if is_checkbox:
                self._set_run_font(first_run, CHECKBOX_FONT)

            # Middle runs: clear completely
            for i in range(start_run_idx + 1, end_run_idx):
                runs[i].text = ''

            # Last run: keep only the text after the placeholder
            last_run = runs[end_run_idx]
            last_run.text = last_run.text[end_char_in_run:]

    def _replace_placeholders(self, doc: Document, checkbox_states: dict, text_replacements: dict):
        """Replaces all placeholders in the document."""
        all_replacements = self._collect_replacements(checkbox_states, text_replacements)

        # Replace in paragraphs
        for paragraph in doc.paragraphs:
            self._replace_in_paragraph(paragraph, all_replacements)

        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._replace_in_paragraph(paragraph, all_replacements)

    @staticmethod
    def _spesen_for_match(match_data: dict) -> tuple:
        """
        Returns (sr_spesen, sra_spesen) as numbers.

        If the match comes from the database, the rates were frozen there on the first
        scrape and are only read here - otherwise a later change of the
        expense regulations would retroactively rewrite a settlement that has already been
        submitted. Only without frozen values is anything calculated.
        """
        if 'sr_spesen' in match_data or 'sra_spesen' in match_data:
            return match_data.get('sr_spesen'), match_data.get('sra_spesen')

        spiel_info = match_data.get('spiel_info', {})
        return calculate_spesen(
            spiel_info.get('spielklasse', ''),
            spiel_info.get('mannschaftsart', ''),
            spiel_info.get('staffel', ''),
            spiel_info.get('heim_team', ''),
            spiel_info.get('gast_team', '')
        )

    def _calculate_spesen_for_match(self, match_data: dict) -> tuple:
        """
        Formats the expenses for a match.

        Whether there is a rate at all is decided solely by the calculator - also
        for cup and friendly matches. A second filter here would be a second opinion on the same question,
        and that is exactly how it once came about that
        league-match rates sat in the database for cup matches.
        """
        sr_spesen, sra_spesen = self._spesen_for_match(match_data)
        sr_spesen_str = format_spesen(sr_spesen)
        sra_spesen_str = format_spesen(sra_spesen)

        if sr_spesen_str:
            logger.info(f"Spesen berechnet: SR={sr_spesen_str}, SRA={sra_spesen_str or '-'}")

        return (sr_spesen_str, sra_spesen_str)

    def _build_expense_replacements(self, expenses: dict,
                                    match_data: dict, sra1_active: bool, sra2_active: bool) -> dict:
        """
        Builds the placeholders for travel costs (km x 0.30 EUR), public transport (OeVM) and the
        total line (expenses + travel costs + OeVM) per person.
        """
        expenses = expenses or {}

        # Numeric expenses for the total calculation
        sr_spesen_num, sra_spesen_num = self._spesen_for_match(match_data)

        # If even the SR rate is unknown, no rate at all has been determined for this match
        # - supra-regional, or a cup/friendly match whose
        # rate depends on the clubs' Spielklasse. Then no
        # total may be printed either: it would consist only of the travel costs, but would look
        # like the final amount, and whoever fills in the expenses by hand
        # would leave a total that is too low underneath.
        #
        # A missing SRA rate with a known SR rate, by contrast, means "no SRA
        # provided" (e.g. Juniorinnen) - there the total of
        # travel costs and OeVM remains correct.
        saetze_bekannt = sr_spesen_num is not None

        # The km rate is frozen when scraping, like the expenses
        km_satz = match_data.get('km_satz') or KM_SATZ_EURO

        replacements = {}
        roles = [
            ('SR', 'sr', sr_spesen_num, True),
            ('SRA1', 'sra1', sra_spesen_num, sra1_active),
            ('SRA2', 'sra2', sra_spesen_num, sra2_active),
        ]

        # For the grand total: all assigned persons must be recorded
        # (an explicit 0 counts as recorded, an empty field does not)
        alle_aktiven_erfasst = True
        einzelsummen = []

        for prefix, key, spesen_num, active in roles:
            km = expenses.get(f'{key}_km')
            oevm = expenses.get(f'{key}_oevm')

            # 0 is a valid value (deliberately recorded), None = not entered
            erfasst = km is not None or oevm is not None
            km_kosten = round(km * km_satz, 2) if km is not None else None
            oevm_betrag = oevm if oevm is not None else None

            # Display: 0 amounts stay empty on the form
            replacements[f'{prefix}_Kilometer'] = format_spesen(km_kosten) if km_kosten else ''
            replacements[f'{prefix}_OEVM'] = format_spesen(oevm_betrag) if oevm_betrag else ''

            # Total only once the person is assigned and their travel costs are recorded.
            # Otherwise an amount would be shown to which the travel costs are still missing.
            komponenten = [v for v in (spesen_num, km_kosten, oevm_betrag) if v is not None]
            berechenbar = komponenten and active and erfasst and saetze_bekannt
            summe = round(sum(komponenten), 2) if berechenbar else None
            replacements[f'{prefix}_Summe'] = format_spesen(summe) if summe else ''

            if active:
                if not erfasst:
                    alle_aktiven_erfasst = False
                elif summe is not None:
                    einzelsummen.append(summe)

        # Grand total over all assigned persons
        if saetze_bekannt and alle_aktiven_erfasst and einzelsummen:
            replacements['Summe'] = format_spesen(round(sum(einzelsummen), 2))
        else:
            replacements['Summe'] = ''

        return replacements

    def render_document(self, match_data: dict, expenses: dict = None) -> bytes:
        """
        Renders a document and returns it as bytes - without a detour via
        the disk. This is the path for downloads: the document is created anew on
        every request from the database rows.

        Args:
                expenses: Optional travel cost/OeVM values
                                    (keys: sr_km, sr_oevm, sra1_km, sra1_oevm, sra2_km, sra2_oevm)
        """
        doc = self._fill_template(match_data, expenses)

        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    def generate_document(self, match_data: dict, output_filename: str = None, expenses: dict = None) -> Path:
        """
        Generates a filled-in document for a match and stores it in
        output_dir.

        Args:
                expenses: Optional travel cost/OeVM values
                                    (keys: sr_km, sr_oevm, sra1_km, sra1_oevm, sra2_km, sra2_oevm)
        """
        if not self.output_dir:
            raise ValueError("Kein output_dir gesetzt - render_document() verwenden")

        doc = self._fill_template(match_data, expenses)

        if not output_filename:
            output_filename = generate_filename_from_match(match_data)

        output_path = self.output_dir / output_filename
        doc.save(output_path)

        logger.info(f"Dokument erstellt: {output_path}")
        return output_path

    def _fill_template(self, match_data: dict, expenses: dict = None):
        """
        Fills the template with the data of a match and returns the
        python-docx document. Common core of render_document()
        and generate_document().
        """
        spiel_info = match_data.get('spiel_info', {})
        schiedsrichter = match_data.get('schiedsrichter', [])
        spielstaette = match_data.get('spielstaette', {})

        doc = Document(self.template_path)
        logger.debug(f"Vorlage geladen für: {spiel_info.get('heim_team', '')} vs {spiel_info.get('gast_team', '')}")

        datum, anstoss = parse_anpfiff(spiel_info.get('anpfiff', ''))
        checkboxes = self._determine_checkboxes(match_data)

        sr_spesen_str, sra_spesen_str = self._calculate_spesen_for_match(match_data)

        sr = self._get_referee_by_role(schiedsrichter, 'SR')
        sra1 = self._get_referee_by_role(schiedsrichter, 'SRA 1')
        sra2 = self._get_referee_by_role(schiedsrichter, 'SRA 2')

        spielort_name = spielstaette.get('name', '')
        spielort_adresse = spielstaette.get('adresse', '')
        spielort_komplett = f"{spielort_name}\n{spielort_adresse}"

        sra1_spesen = sra_spesen_str if sra1.get('name') else ''
        sra2_spesen = sra_spesen_str if sra2.get('name') else ''

        expense_replacements = self._build_expense_replacements(
            expenses, match_data,
            sra1_active=bool(sra1.get('name')), sra2_active=bool(sra2.get('name'))
        )

        text_replacements = {
            **expense_replacements,
            'HEIM_TEAM': spiel_info.get('heim_team', ''),
            'GAST_TEAM': spiel_info.get('gast_team', ''),
            'SPIELKLASSE': spiel_info.get('spielklasse', ''),
            'SPIELNUMMER': match_data.get('spielnummer') or '',
            'DATUM': datum,
            'ANSTOSS': anstoss,
            'SPIELORT': spielort_komplett,
            'SR_NAME': format_name_nachname_vorname(sr.get('name', '')),
            'SR_STRASSE': sr.get('strasse', ''),
            'SR_PLZ_ORT': sr.get('plz_ort', ''),
            'SRA1_NAME': format_name_nachname_vorname(sra1.get('name', '')),
            'SRA1_STRASSE': sra1.get('strasse', ''),
            'SRA1_PLZ_ORT': sra1.get('plz_ort', ''),
            'SRA2_NAME': format_name_nachname_vorname(sra2.get('name', '')),
            'SRA2_STRASSE': sra2.get('strasse', ''),
            'SRA2_PLZ_ORT': sra2.get('plz_ort', ''),
            'SR_Spesen': sr_spesen_str,
            'SR1_Spesen': sra1_spesen,
            'SR2_Spesen': sra2_spesen,
        }

        self._replace_placeholders(doc, checkboxes, text_replacements)

        return doc

    def generate_all_documents(self, matches_data: list, expenses_map: dict = None) -> list:
        """
        Generates documents for all matches.

        Args:
                expenses_map: Optional dict {(heim, gast, datum_iso): expenses}
                                            with stored travel costs/OeVM per match.
        """
        logger.info(f"Generiere {len(matches_data)} Dokumente...")
        expenses_map = expenses_map or {}

        generated_files = []
        for i, match_data in enumerate(matches_data, 1):
            try:
                spiel_info = match_data.get('spiel_info', {})
                heim = spiel_info.get('heim_team', 'Unbekannt')
                gast = spiel_info.get('gast_team', 'Unbekannt')
                datum_iso = extract_iso_date_from_anpfiff(spiel_info.get('anpfiff', ''))
                expenses = expenses_map.get((heim, gast, datum_iso))

                logger.info(f"[{i}/{len(matches_data)}] Verarbeite: {heim} vs {gast}")
                output_path = self.generate_document(match_data, expenses=expenses)
                generated_files.append(output_path)
                logger.info(f"[{i}/{len(matches_data)}] ✓ Erstellt")
            except Exception as e:
                logger.error(f"[{i}/{len(matches_data)}] ✗ Fehler: {e}")
                continue

        logger.info(f"Erfolgreich {len(generated_files)}/{len(matches_data)} Dokumente generiert")
        return generated_files