"""
NOFV generator - fills in the NOFV travel expense settlement (Reisekostenabrechnung).

Unlike the TFV form, on which the whole crew appears, the
NOFV receipt is a settlement per person: under §9 no. 7.15 of the finance regulations (Finanzordnung)
every referee and assistant hands the host club (platzbauender Verein) their
own receipt. The template is therefore an Excel file with one sheet, which is
copied and filled once per assigned person - a workbook
with three sheets becomes a three-page PDF.

Travel cost fields and the total remain formulas, so that the Excel file keeps
calculating when entries are added by hand.
"""
import copy
import re
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment

from generator.docx_generator import KM_SATZ_EURO, format_name_nachname_vorname
from generator.spesen_calculator import calculate_spesen
from utils.logger import setup_logger
from utils.match_utils import parse_anpfiff

logger = setup_logger("nofv_generator")

# (role in DFBnet, entry "Einsatz als" (duty as), prefix of the travel costs, sheet name)
ROLLEN = [
    ("SR", "Schiedsrichter", "sr", "SR"),
    ("SRA 1", "Schiedsrichterassistent 1", "sra1", "SRA 1"),
    ("SRA 2", "Schiedsrichterassistent 2", "sra2", "SRA 2"),
]

DATUMSFORMAT = "DD.MM.YYYY"

# Cells of the template (sheet "Table 1", form version of 15.08.2024)
ZELLE_NAME = "E8"
ZELLE_STRASSE = "E9"
ZELLE_WOHNORT = "E10"
ZELLE_EINSATZ = "E12"
ZELLE_SPIELKLASSE = "E13"
ZELLE_HEIM = "E14"
ZELLE_GAST = "I14"
ZELLE_DATUM = "E15"
ZELLE_SPIELNUMMER = "J15"
ZELLE_HINREISE_DATUM = "E16"
ZELLE_HINREISE_STRECKE = "I16"
ZELLE_RUECKREISE_DATUM = "E17"
ZELLE_RUECKREISE_STRECKE = "I17"
ZELLE_AUFWAND = "J20"
ZELLE_BAHN = "J24"
ZELLE_KM = "E26"
ZELLE_KM_SATZ = "G26"
ZELLE_PKW = "J26"
ZELLE_GESAMT = "J31"
ZELLE_IN_WORTEN = "E32"

# Fields with free text of unknown length. The template sets them in 16 pt, a
# long club name would run over the edge and be cut off.
ZELLEN_SCHRUMPFEN = (
    ZELLE_NAME, ZELLE_STRASSE, ZELLE_WOHNORT, ZELLE_EINSATZ, ZELLE_SPIELKLASSE,
    ZELLE_HEIM, ZELLE_GAST, ZELLE_HINREISE_STRECKE, ZELLE_RUECKREISE_STRECKE,
    ZELLE_IN_WORTEN,
)

# Empty fields should stay empty instead of showing "0,00 €". The total appears
# only once expense allowance and travel costs are there - as with the
# TFV form, where a total without travel costs would look like the final amount.
FORMEL_PKW = f'=IF({ZELLE_KM}="","",{ZELLE_KM}*{ZELLE_KM_SATZ})'
FORMEL_GESAMT = (
    f'=IF(OR({ZELLE_AUFWAND}="",AND({ZELLE_KM}="",{ZELLE_BAHN}="")),"",'
    f'SUM({ZELLE_AUFWAND},J22,{ZELLE_BAHN},{ZELLE_PKW},J30))'
)


# ===== Amount in words =====

_EINER = ["", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun",
          "zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn",
          "siebzehn", "achtzehn", "neunzehn"]
_ZEHNER = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig",
           "achtzig", "neunzig"]


def _unter_tausend(n: int) -> str:
    hunderter, rest = divmod(n, 100)
    teile = []
    if hunderter:
        teile.append(_EINER[hunderter] + "hundert")
    if rest < 20:
        teile.append(_EINER[rest])
    else:
        zehner, einer = divmod(rest, 10)
        teile.append((_EINER[einer] + "und" if einer else "") + _ZEHNER[zehner])
    return "".join(teile)


def zahl_in_worten(n: int) -> str:
    """Whole number from 0 to 999,999 as a German number word ("dreihundertzehn")."""
    if n == 0:
        return "null"
    if n == 1:
        return "eins"

    tausender, rest = divmod(n, 1000)
    wort = (_unter_tausend(tausender) + "tausend" if tausender else "") + _unter_tausend(rest)

    # "einundzwanzig" yes, but at the end "...hunderteins" instead of "...hundertein"
    return wort + "s" if rest % 100 == 1 else wort


def betrag_in_worten(betrag: float) -> str:
    """310.5 -> "dreihundertzehn Euro fünfzig Cent"."""
    cent_gesamt = round(betrag * 100)
    euro, cent = divmod(cent_gesamt, 100)

    def vor_einheit(n: int) -> str:
        # "ein Euro", but "einhunderteins Euro"
        return "ein" if n == 1 else zahl_in_worten(n)

    text = f"{vor_einheit(euro)} Euro"
    if cent:
        text += f" {vor_einheit(cent)} Cent"
    return text


# ===== Helpers =====

def _ort_aus_plz_ort(plz_ort: str) -> str:
    """"99438 Bad Berka" -> "Bad Berka"."""
    return re.sub(r"^\s*\d{5}\s+", "", plz_ort or "").strip()


def _ort_aus_adresse(adresse: str) -> str:
    """"Am Sportzentrum 17, 06792 Sandersdorf" -> "Sandersdorf"."""
    treffer = re.search(r"\d{5}\s+(.+)$", adresse or "")
    return treffer.group(1).strip() if treffer else ""


def _datum(anpfiff: str) -> Optional[date]:
    datum, _ = parse_anpfiff(anpfiff or "")
    treffer = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", datum.strip())
    if not treffer:
        return None
    tag, monat, jahr = (int(x) for x in treffer.groups())
    return date(jahr, monat, tag)


class NofvGenerator:
    """Creates the NOFV travel expense settlement: one sheet per assigned person."""

    def __init__(self, template_path):
        self.template_path = Path(template_path)

        if not self.template_path.exists():
            raise FileNotFoundError(f"Vorlage nicht gefunden: {self.template_path}")

        # The images (NOFV logo) straight from the archive: openpyxl attaches loaded
        # images to a buffer that it closes after loading - such an image can
        # then no longer be saved or copied.
        with zipfile.ZipFile(self.template_path) as archiv:
            self._bilder = [
                archiv.read(name) for name in sorted(archiv.namelist())
                if name.startswith("xl/media/")
            ]

    @staticmethod
    def _spesen_for_match(match_data: dict) -> Tuple[Optional[float], Optional[float]]:
        """Frozen rates from the database, otherwise freshly calculated."""
        if 'sr_spesen' in match_data or 'sra_spesen' in match_data:
            return match_data.get('sr_spesen'), match_data.get('sra_spesen')

        spiel_info = match_data.get('spiel_info', {})
        return calculate_spesen(
            spiel_info.get('spielklasse', ''),
            spiel_info.get('mannschaftsart', ''),
            spiel_info.get('staffel', ''),
            spiel_info.get('heim_team', ''),
            spiel_info.get('gast_team', ''),
        )

    @staticmethod
    def _besetzte_rollen(match_data: dict) -> List[Tuple[dict, str, str, str, str]]:
        """
        The assigned persons in form order.

        Without any assignment a sheet is still created for the
        referee - with the match data but without a person - instead of an
        empty file.
        """
        personen = {
            ref.get('rolle'): ref
            for ref in match_data.get('schiedsrichter', [])
            if ref.get('name')
        }

        besetzt = [
            (personen[rolle], rolle, einsatz, praefix, blatt)
            for rolle, einsatz, praefix, blatt in ROLLEN
            if rolle in personen
        ]

        if not besetzt:
            rolle, einsatz, praefix, blatt = ROLLEN[0]
            besetzt = [({}, rolle, einsatz, praefix, blatt)]

        return besetzt

    def _kopiere_blatt(self, workbook, vorlage, titel: str):
        """
        Copies the template sheet including everything copy_worksheet leaves out.

        openpyxl takes over cells, formats, column widths and merged
        cells, but not images (the NOFV logo), print area and view.
        Without a print area LibreOffice spreads the sheet over several pages.
        """
        blatt = workbook.copy_worksheet(vorlage)
        blatt.title = titel
        blatt.print_area = vorlage.print_area
        blatt.sheet_properties.pageSetUpPr = copy.copy(vorlage.sheet_properties.pageSetUpPr)
        blatt.sheet_view.showGridLines = vorlage.sheet_view.showGridLines

        for bild, daten in zip(vorlage._images, self._bilder):
            kopie = Image(BytesIO(daten))
            kopie.anchor = copy.deepcopy(bild.anchor)
            kopie.width, kopie.height = bild.width, bild.height
            blatt.add_image(kopie)

        return blatt

    def _fuelle_blatt(self, blatt, match_data: dict, person: dict, einsatz: str,
                      aufwand: Optional[float], km: Optional[float], oevm: Optional[float],
                      km_satz: float):
        spiel_info = match_data.get('spiel_info', {})
        spielstaette = match_data.get('spielstaette', {})
        spieldatum = _datum(spiel_info.get('anpfiff', ''))

        wohnort = _ort_aus_plz_ort(person.get('plz_ort', ''))
        spielort = _ort_aus_adresse(spielstaette.get('adresse', '')) or spielstaette.get('name', '')

        blatt[ZELLE_NAME] = format_name_nachname_vorname(person.get('name', ''))
        blatt[ZELLE_STRASSE] = person.get('strasse', '')
        blatt[ZELLE_WOHNORT] = person.get('plz_ort', '')
        blatt[ZELLE_EINSATZ] = einsatz if person else ''
        blatt[ZELLE_SPIELKLASSE] = spiel_info.get('staffel') or spiel_info.get('spielklasse', '')
        blatt[ZELLE_HEIM] = spiel_info.get('heim_team', '')
        blatt[ZELLE_GAST] = spiel_info.get('gast_team', '')
        blatt[ZELLE_SPIELNUMMER] = match_data.get('spielnummer') or ''

        if spieldatum:
            for zelle in (ZELLE_DATUM, ZELLE_HINREISE_DATUM, ZELLE_RUECKREISE_DATUM):
                blatt[zelle] = spieldatum
                blatt[zelle].number_format = DATUMSFORMAT

        # The referee enters times themselves - only they know the departure.
        if wohnort and spielort:
            blatt[ZELLE_HINREISE_STRECKE] = f"{wohnort} - {spielort}"
            blatt[ZELLE_RUECKREISE_STRECKE] = f"{spielort} - {wohnort}"

        if aufwand is not None:
            blatt[ZELLE_AUFWAND] = aufwand

        # 0 km / 0 € is recorded and counts for the total, but is only
        # entered if otherwise no travel costs at all would be there.
        if km:
            blatt[ZELLE_KM] = km
        if oevm:
            blatt[ZELLE_BAHN] = oevm
        # Otherwise the total formula would stay empty while "In Worten" (in words) already
        # states an amount. The 0 lands in the field that was recorded.
        if not km and not oevm:
            if km is not None:
                blatt[ZELLE_KM] = 0
            elif oevm is not None:
                blatt[ZELLE_BAHN] = 0

        blatt[ZELLE_KM_SATZ] = km_satz
        blatt[ZELLE_PKW] = FORMEL_PKW
        blatt[ZELLE_GESAMT] = FORMEL_GESAMT

        erfasst = km is not None or oevm is not None
        if aufwand is not None and erfasst:
            gesamt = round(aufwand + round((km or 0) * km_satz, 2) + (oevm or 0), 2)
            blatt[ZELLE_IN_WORTEN] = betrag_in_worten(gesamt)

        for zelle in ZELLEN_SCHRUMPFEN:
            ausrichtung = copy.copy(blatt[zelle].alignment)
            blatt[zelle].alignment = Alignment(
                horizontal=ausrichtung.horizontal,
                vertical=ausrichtung.vertical or "center",
                shrink_to_fit=True,
            )

    def render_workbook(self, match_data: dict, expenses: dict = None) -> bytes:
        """
        Renders the settlement of a match as an Excel workbook (one sheet per
        assigned person) and returns it as bytes.

        Args:
                expenses: Optional travel cost/OeVM values
                                    (keys: sr_km, sr_oevm, sra1_km, sra1_oevm, sra2_km, sra2_oevm)
        """
        expenses = expenses or {}
        sr_spesen, sra_spesen = self._spesen_for_match(match_data)
        km_satz = match_data.get('km_satz') or KM_SATZ_EURO

        workbook = load_workbook(self.template_path)
        vorlage = workbook.active

        for bild, daten in zip(vorlage._images, self._bilder):
            bild.ref = BytesIO(daten)

        besetzt = self._besetzte_rollen(match_data)

        # First take all copies from the untouched template, then fill
        blaetter = [vorlage] + [
            self._kopiere_blatt(workbook, vorlage, blatt_titel)
            for _, _, _, _, blatt_titel in besetzt[1:]
        ]
        vorlage.title = besetzt[0][4]

        for blatt, (person, rolle, einsatz, praefix, _) in zip(blaetter, besetzt):
            aufwand = sr_spesen if rolle == "SR" else sra_spesen
            self._fuelle_blatt(
                blatt, match_data, person, einsatz, aufwand,
                expenses.get(f"{praefix}_km"), expenses.get(f"{praefix}_oevm"), km_satz,
            )

        spiel_info = match_data.get('spiel_info', {})
        logger.info(
            f"NOFV-Abrechnung: {spiel_info.get('heim_team', '')} vs "
            f"{spiel_info.get('gast_team', '')}, {len(blaetter)} Blätter"
        )

        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()
