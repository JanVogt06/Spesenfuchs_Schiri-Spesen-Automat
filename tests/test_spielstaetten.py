"""
Karte der besuchten Spielstaetten: echte Wegwerf-Datenbank mit Ansetzungen,
Spielberichten und geleiteten Spielen; die Adresssuche ist eine Attrappe.
"""
from datetime import date

import pytest

from db.database import get_connection
from db.matches import upsert_match
from db.season import replace_saison
from db.spielberichte import get_spielorte, speichere_bericht
from db_helpers import spiel
from api_hilfen import fremder  # noqa: F401 - Fixture
from utils import eigene_spiele
from utils.spielstaetten import besuchte_spielstaetten

HEUTE = date(2026, 11, 24)


@pytest.fixture
def adresssuche(monkeypatch):
    bekannt = {"Waldweg 1, 99999 Irgendwo": (50.0, 11.0), "Auenweg, 07318 Saalfeld": (50.6, 11.3)}

    def geocode_bekannt(adresse, ort=None):
        punkt = bekannt.get(adresse)
        return ({"lat": punkt[0], "lon": punkt[1], "genauigkeit": "adresse"} if punkt else None), False

    monkeypatch.setattr(eigene_spiele, "geocode_bekannt", geocode_bekannt)
    return bekannt


def ansetzung(user_id, tag, selbst=0, **kw):
    daten = spiel(tag=tag, **kw)
    if selbst is not None:
        daten["schiedsrichter"][selbst]["selbst"] = True
    return upsert_match(user_id, daten, tag, 30.0, 20.0, 0.30)


def bericht(user_id, spiel_id, datum, heim="FC Bericht", staette=None, ergebnis=None):
    staette = staette or {"name": "Kunstrasen An der Aue", "ort": "07318 Saalfeld", "strasse": "Auenweg"}
    zeile = {"dfb_spiel_id": spiel_id, "datum": datum, "uhrzeit": "14:00", "gruppe": "", "nummer": "",
             "heim": heim, "gast": "SV Gast", "ergebnis": ""}
    daten = {"kosten": {}, "spielstaette": staette, "ergebnis": ergebnis or {"endstand": "2:1", "wertung": ""}}
    return speichere_bericht(user_id, "25/26", zeile, daten, {})


def karte(user_id):
    return besuchte_spielstaetten(user_id, frist=float("inf"), heute=HEUTE)


class TestBesuchtePlaetze:
    def test_nur_vergangene_spiele(self, user, adresssuche):
        ansetzung(user["id"], "2026-09-05")
        ansetzung(user["id"], "2026-11-24", heim="FC Heute", staette="Heute-Platz")
        ansetzung(user["id"], "2026-12-05", heim="FC Zukunft", staette="Zukunfts-Platz")

        daten = karte(user["id"])

        assert [o["name"] for o in daten["orte"]] == ["Sportplatz Am Wald"]
        assert daten["orte"][0]["spiele"] == [{"datum": "2026-09-05", "saison": "26/27", "heim": "FC Heim",
                                               "gast": "SV Gast", "rolle": "SR"}]
        assert (daten["orte"][0]["lat"], daten["orte"][0]["genauigkeit"]) == (50.0, "adresse")

    def test_zurueckgezogene_ansetzung_zaehlt_nicht(self, user, adresssuche):
        mid = ansetzung(user["id"], "2026-09-05")
        conn = get_connection()
        conn.execute("UPDATE matches SET missing_since = '2026-09-01' WHERE id = ?", (mid,))
        conn.commit()
        conn.close()

        assert karte(user["id"])["orte"] == []

    def test_dfbnet_koordinate_hat_vorrang(self, user, adresssuche):
        daten = spiel(tag="2026-09-05")
        daten["spielstaette"].update(lat=50.5, lon=11.5)
        upsert_match(user["id"], daten, "2026-09-05", 30.0, 20.0, 0.30)

        ort = karte(user["id"])["orte"][0]
        assert (ort["lat"], ort["lon"], ort["genauigkeit"]) == (50.5, 11.5, "platz")

    def test_gleicher_platz_wird_ein_punkt_mit_allen_spielen(self, user, adresssuche):
        ansetzung(user["id"], "2026-09-05")
        ansetzung(user["id"], "2026-10-10", heim="FC Zwei", selbst=1)

        (ort,) = karte(user["id"])["orte"]
        assert ort["anzahl"] == 2
        assert [s["datum"] for s in ort["spiele"]] == ["2026-10-10", "2026-09-05"]
        assert [s["rolle"] for s in ort["spiele"]] == ["SRA 1", "SR"]

    def test_spielberichte_aelterer_saisons(self, user, adresssuche):
        bericht(user["id"], "B1", "2026-03-01")
        replace_saison(user["id"], "25/26", [{"datum": "2026-03-01", "uhrzeit": "14:00", "liga": "", "heim": "FC Bericht 2.",
                                             "gast": "SV Gast", "ergebnis": "2:1", "karten": {}, "gespann": [],
                                             "eigene_rolle": "SRA 2"}], [], {})

        (ort,) = karte(user["id"])["orte"]
        assert ort["name"] == "Kunstrasen An der Aue"
        assert ort["adresse"] == "Auenweg, 07318 Saalfeld"
        assert ort["spiele"][0]["rolle"] == "SRA 2"
        assert ort["spiele"][0]["saison"] == "25/26"

    def test_ausgefallene_spiele_und_doppelte_berichte(self, user, adresssuche):
        daten = spiel(tag="2026-09-05")
        daten["spiel_info"]["dfb_spiel_id"] = "S1"
        daten["schiedsrichter"][0]["selbst"] = True
        upsert_match(user["id"], daten, "2026-09-05", 30.0, 20.0, 0.30)
        bericht(user["id"], "S1", "2026-09-05")
        bericht(user["id"], "B2", "2026-03-01", ergebnis={"endstand": "", "wertung": "Spielausfall"})

        daten = karte(user["id"])
        assert daten["spiele"] == 1
        assert [o["name"] for o in daten["orte"]] == ["Sportplatz Am Wald"]

    def test_unauffindbar_und_offen(self, user, adresssuche, monkeypatch):
        ansetzung(user["id"], "2026-09-05", staette="Nirgends", adresse="Unbekannt 1, 11111 Nirgends")
        assert (karte(user["id"])["ohne_treffer"], karte(user["id"])["offen"]) == (1, 0)

        monkeypatch.setattr(eigene_spiele, "geocode_bekannt", lambda a, o=None: (None, True))
        daten = besuchte_spielstaetten(user["id"], frist=0.0, heute=HEUTE)
        assert (daten["offen"], daten["ohne_treffer"], daten["orte"]) == (1, 0, [])

    def test_fremde_spiele_bleiben_fremd(self, user, fremder, adresssuche):
        ansetzung(fremder["id"], "2026-09-05")
        bericht(fremder["id"], "B1", "2026-03-01")
        assert karte(user["id"])["orte"] == []


def test_spielorte_liest_staette_und_ausfall(user):
    bericht(user["id"], "B1", "2026-03-01", ergebnis={"endstand": "", "wertung": "Nichtantritt"})
    (eintrag,) = get_spielorte(user["id"])
    assert eintrag["ausgefallen"] is True
    assert eintrag["spielstaette"]["name"] == "Kunstrasen An der Aue"
