"""
Season arithmetic in the DFBnet format.

A season begins on 1 July and ends on 30 June of the following year. DFBnet
names it with the two two-digit years: "25/26" runs from
01.07.2025 to 30.06.2026.
"""
import re
from datetime import date, datetime
from typing import Optional, Tuple

_SAISON = re.compile(r"\s*(\d{2})/(\d{2})\s*")


def saison_start_jahr(saison: str, heute: Optional[date] = None) -> Optional[int]:
    """
    The calendar year in which a season begins: "25/26" -> 2025.

    Two-digit years need a century. Anything that would lie more than one year
    after the current year belongs to the 20th century - a
    "referee since 1995" thus lands in "95/96" and not in 2095.
    """
    treffer = _SAISON.fullmatch(saison or "")
    if not treffer:
        return None

    kurz = int(treffer.group(1))
    obergrenze = (heute or date.today()).year + 1
    # In the century of the upper bound, if necessary the one before. With "% 100" on
    # the bound this broke in the year 2099, where the bound would become 0.
    jahr = obergrenze // 100 * 100 + kurz
    return jahr - 100 if jahr > obergrenze else jahr


def saison_fuer_datum(tag: date) -> str:
    """The season a day falls into: 15.03.2026 -> "25/26"."""
    start = tag.year if tag.month >= 7 else tag.year - 1
    return f"{start % 100:02d}/{(start + 1) % 100:02d}"


def saison_zeitraum(saison: str) -> Optional[Tuple[date, date]]:
    """First and last day of a season: "25/26" -> (01.07.2025, 30.06.2026)."""
    start = saison_start_jahr(saison)
    if start is None:
        return None
    return date(start, 7, 1), date(start + 1, 6, 30)


def parse_deutsches_datum(text: str) -> Optional[date]:
    """'26.01.2019' -> date(2019, 1, 26); anything else -> None."""
    try:
        return datetime.strptime((text or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        return None
