"""
Saisonrechnung im DFBnet-Format.

Eine Saison beginnt am 1. Juli und endet am 30. Juni des Folgejahres. DFBnet
nennt sie mit den beiden zweistelligen Jahreszahlen: "25/26" laeuft vom
01.07.2025 bis zum 30.06.2026.
"""
import re
from datetime import date, datetime
from typing import Optional, Tuple

_SAISON = re.compile(r"\s*(\d{2})/(\d{2})\s*")


def saison_start_jahr(saison: str, heute: Optional[date] = None) -> Optional[int]:
    """
    Das Kalenderjahr, in dem eine Saison beginnt: "25/26" -> 2025.

    Zweistellige Jahre brauchen ein Jahrhundert. Alles, was mehr als ein Jahr
    nach dem laufenden Jahr laege, gehoert ins 20. Jahrhundert - ein
    "Schiedsrichter seit 1995" landet so in "95/96" und nicht in 2095.
    """
    treffer = _SAISON.fullmatch(saison or "")
    if not treffer:
        return None

    kurz = int(treffer.group(1))
    grenze = ((heute or date.today()).year + 1) % 100
    return (1900 if kurz > grenze else 2000) + kurz


def saison_fuer_datum(tag: date) -> str:
    """Die Saison, in die ein Tag faellt: 15.03.2026 -> "25/26"."""
    start = tag.year if tag.month >= 7 else tag.year - 1
    return f"{start % 100:02d}/{(start + 1) % 100:02d}"


def saison_zeitraum(saison: str) -> Optional[Tuple[date, date]]:
    """Erster und letzter Tag einer Saison: "25/26" -> (01.07.2025, 30.06.2026)."""
    start = saison_start_jahr(saison)
    if start is None:
        return None
    return date(start, 7, 1), date(start + 1, 6, 30)


def parse_deutsches_datum(text: str) -> Optional[date]:
    """'26.01.2019' -> date(2019, 1, 26); alles andere -> None."""
    try:
        return datetime.strptime((text or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        return None
