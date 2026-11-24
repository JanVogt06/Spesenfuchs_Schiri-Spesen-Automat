"""
A complete retrieval against the real DFBnet - end to end.

Runs only if SPESENFUCHS_E2E=1 is set and credentials are in
DFB_USERNAME/DFB_PASSWORD (in the pipeline from the GitHub secrets, see
.github/workflows/e2e.yml). Otherwise it is skipped - a normal pytest never
logs in to DFBnet.

What happens: login, assignments, master data, seasons, observations and
match reports, all into a fresh throwaway database, then an expense
receipt. As in the nightly run, only the current season is read: the test
reports all earlier ones as already done. A run over all seasons since the
first assignment (including hundreds of match reports) would be too heavy
for every push, both for DFBnet and for the run time.

PRIVACY: The repository is public, and so are the pipeline logs. NOTHING
that was read from DFBnet may leave this test - no names, teams, dates and
not even counts. Therefore:

- no bare asserts: pytest would print their values ("assert 0 > 0").
  Only the names of the failed checks are reported, fixed in the code.
- every exception is reduced to its type; its message might contain data.
- the pipeline calls pytest with --show-capture=no and --tb=no: the
  scraper's loggers write teams and dates, and this way they appear nowhere.
"""
import os
import re
from datetime import date
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("SPESENFUCHS_E2E") != "1"
        or not os.environ.get("DFB_USERNAME") or not os.environ.get("DFB_PASSWORD"),
        reason="nur mit SPESENFUCHS_E2E=1 und DFB-Zugangsdaten",
    ),
]


def _alle_frueheren_saisons(heute: date) -> set:
    from utils.saison_utils import saison_fuer_datum

    laufende = saison_fuer_datum(heute)
    return {saison_fuer_datum(date(jahr, 7, 1)) for jahr in range(1980, heute.year + 1)} - {laufende}


def _anzahl(sql: str, *parameter) -> int:
    from db.database import get_connection

    conn = get_connection()
    try:
        return conn.execute(sql, parameter).fetchone()[0]
    finally:
        conn.close()


def _entpackt(inhalt: bytes) -> bytes:
    """DOCX and XLSX are ZIP archives - the identifier is in their XML."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(inhalt)) as archiv:
        return b"".join(archiv.read(name) for name in archiv.namelist() if name.endswith(".xml"))


def _gesamtlauf(user_id: int, monkeypatch) -> dict:
    """The retrieval and all checks; check -> passed (only yes/no)."""
    import main
    from db.matches import get_match, get_matches_for_user
    from db.season import get_saison
    from db.stammdaten import get_stammdaten
    from generator.docx_generator import SpesenGenerator
    from generator.nofv_generator import NofvGenerator
    from generator.spesen_calculator import ist_nofv_spiel
    from utils.saison_utils import saison_fuer_datum

    heute = date.today()
    frueher = _alle_frueheren_saisons(heute)

    # Read only the current season, as in the nightly run
    monkeypatch.setattr(main, "get_komplette_saisons", lambda uid: set(frueher))
    monkeypatch.setattr(main, "get_fertige_beobachtungs_saisons", lambda uid, quelle: set(frueher))
    monkeypatch.setattr(main, "get_fertige_bericht_saisons", lambda uid: set(frueher))

    main.scrape_matches(
        username=os.environ["DFB_USERNAME"],
        password=os.environ["DFB_PASSWORD"],
        user_id=user_id,
    )

    spiele = get_matches_for_user(user_id)
    stammdaten = get_stammdaten(user_id) or {}
    saison = get_saison(user_id, saison_fuer_datum(heute)) or {}

    pruefungen = {
        "Ansetzungen gelesen": bool(spiele),
        "jede Ansetzung mit DFBnet-ID": all(s.get("dfb_spiel_id") for s in spiele),
        "jede Ansetzung mit Datum": all(s["datum"] != "1900-01-01" for s in spiele),
        "jede Ansetzung mit Teams oder Spielstaette": all(
            (s["heim_team"] and s["gast_team"]) or s["staette_name"] for s in spiele),
        "Gespann gelesen": any(s["schiedsrichter"] for s in spiele),
        "Spielkennung zugeordnet": any(s.get("spielnummer") for s in spiele),
        "Stammdaten gelesen": bool(re.fullmatch(r"\d{2}\.\d{2}\.\d{4}",
                                                stammdaten.get("schiedsrichter_seit") or ""))
                              and bool(stammdaten.get("sr_gebiet")),
        "laufende Saison gelesen": bool(saison.get("einsaetze")),
        "Beobachtungen gelesen": _anzahl(
            "SELECT COUNT(*) FROM beobachtung_saisons WHERE user_id = ?", user_id) > 0,
        "Einsatzplan der Spielberichte gelesen": _anzahl(
            "SELECT COUNT(*) FROM spielbericht_saisons WHERE user_id = ?", user_id) > 0,
    }

    # A receipt from a stored match with a match identifier
    quittung_ok = False
    kandidat = next((s for s in spiele if s.get("spielnummer") and s["heim_team"]), None)
    if kandidat:
        vorlagen = Path(main.__file__).resolve().parent / "data"
        spiel = get_match(kandidat["id"])
        if ist_nofv_spiel(spiel["spiel_info"]):
            inhalt = NofvGenerator(vorlagen / "SR-Reisekostenabrechnung_NOFV.xlsx").render_workbook(spiel)
        else:
            inhalt = SpesenGenerator(vorlagen / "Spesenabrechnung_Vorlage.docx").render_document(spiel)
        quittung_ok = spiel["spielnummer"].encode() in _entpackt(inhalt)
    pruefungen["Spielkennung auf der Quittung"] = quittung_ok

    return pruefungen


def test_gesamtlauf(user, monkeypatch):
    try:
        pruefungen = _gesamtlauf(user["id"], monkeypatch)
    except Exception as fehler:
        # Only the type - the message might contain data that was read
        pytest.fail(f"Gesamtlauf abgebrochen ({type(fehler).__name__})", pytrace=False)

    fehlgeschlagen = [name for name, ok in pruefungen.items() if not ok]
    if fehlgeschlagen:
        pytest.fail("Fehlgeschlagene Pruefungen: " + ", ".join(fehlgeschlagen), pytrace=False)
