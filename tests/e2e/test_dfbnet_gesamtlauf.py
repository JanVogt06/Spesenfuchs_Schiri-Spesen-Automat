"""
Ein kompletter Abruf gegen das echte DFBnet - Ende zu Ende.

Laeuft nur, wenn SPESENFUCHS_E2E=1 gesetzt ist und Zugangsdaten in
DFB_USERNAME/DFB_PASSWORD stehen (in der Pipeline aus den GitHub-Secrets,
siehe .github/workflows/e2e.yml). Sonst wird er uebersprungen - ein normales
pytest loggt sich nie bei DFBnet ein.

Was passiert: Login, Ansetzungen, Stammdaten, Saisons, Beobachtungen und
Spielberichte, alles in eine frische Wegwerf-Datenbank, danach eine
Spesenquittung. Wie im Nachtlauf wird nur die laufende Saison gelesen: der
Test meldet alle frueheren als bereits fertig. Ein Lauf ueber alle Saisons
seit dem ersten Einsatz (samt hunderter Spielberichte) waere fuer jeden Push
zu schwer, fuer DFBnet wie fuer die Laufzeit.

DATENSCHUTZ: Das Repository ist oeffentlich, die Logs der Pipeline auch. Aus
diesem Test darf NICHTS nach aussen, was bei DFBnet gelesen wurde - keine
Namen, Teams, Termine und auch keine Anzahlen. Deshalb:

- keine nackten asserts: pytest wuerde deren Werte ausgeben ("assert 0 > 0").
  Gemeldet werden nur die Namen der fehlgeschlagenen Pruefungen, fest im Code.
- jede Ausnahme wird auf ihren Typ reduziert; ihre Meldung koennte Daten
  enthalten.
- die Pipeline ruft pytest mit --show-capture=no und --tb=no auf: die Logger
  des Scrapers schreiben Teams und Termine, und die erscheinen so nirgends.
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
    """DOCX und XLSX sind ZIP-Archive - die Kennung steht in deren XML."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(inhalt)) as archiv:
        return b"".join(archiv.read(name) for name in archiv.namelist() if name.endswith(".xml"))


def _gesamtlauf(user_id: int, monkeypatch) -> dict:
    """Der Abruf und alle Pruefungen; Pruefung -> bestanden (nur Ja/Nein)."""
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

    # Nur die laufende Saison lesen, wie im Nachtlauf
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

    # Eine Quittung aus einem gespeicherten Spiel mit Spielkennung
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
        # Nur der Typ - die Meldung koennte gelesene Daten enthalten
        pytest.fail(f"Gesamtlauf abgebrochen ({type(fehler).__name__})", pytrace=False)

    fehlgeschlagen = [name for name, ok in pruefungen.items() if not ok]
    if fehlgeschlagen:
        pytest.fail("Fehlgeschlagene Pruefungen: " + ", ".join(fehlgeschlagen), pytrace=False)
