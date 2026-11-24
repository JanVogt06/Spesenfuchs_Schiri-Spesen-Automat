"""
Statistik ueber die eigenen Spiele: echte Wegwerf-Datenbank, Adresssuche und
Routenplaner als Attrappen.
"""
from datetime import date

import pytest

from db.matches import set_official_expenses, upsert_match
from db.stammdaten import upsert_stammdaten
from db_helpers import spiel
from utils import eigene_spiele, statistik as modul
from utils.routing import Entfernungen, RoutingNichtErreichbar
from utils.statistik import statistik

HEUTE = date(2026, 11, 24)

# Wohnorte und Plaetze: 0,1 Grad Breite = 11,1 km
ORTE = {
    "Weg 1, 99999 Irgendwo": (50.1, 11.0),
    "Weg 2, 99999 Irgendwo": (50.2, 11.0),
    "Waldweg 1, 99999 Irgendwo": (50.0, 11.0),
}


@pytest.fixture
def dienste(monkeypatch):
    gefragt = []

    def bekannt(adresse, ort=None):
        punkt = ORTE.get(adresse)
        return ({"lat": punkt[0], "lon": punkt[1], "genauigkeit": "adresse"} if punkt else None), False

    def entfernungen(quellen, ziele, frist=None):
        gefragt.append((list(quellen), list(ziele)))
        return Entfernungen([[abs(q[0] - z[0]) * 111_000 for z in ziele] for q in quellen], 0)

    monkeypatch.setattr(eigene_spiele, "geocode_bekannt", bekannt)
    monkeypatch.setattr(modul, "entfernungen", entfernungen)
    return gefragt


def anlegen(user_id, tag, selbst=None, sr=30.0, sra=20.0, **kw):
    daten = spiel(tag=tag, **kw)
    if selbst is not None:
        daten["schiedsrichter"][selbst]["selbst"] = True
    return upsert_match(user_id, daten, tag, sr, sra, 0.30)


def auswerten(user_id, saison=None):
    return statistik(user_id, saison, frist=float("inf"), heute=HEUTE)


class TestSpesen:
    def test_eigene_rolle_aus_der_ansetzung(self, user, dienste):
        anlegen(user["id"], "2026-09-05", selbst=0)
        anlegen(user["id"], "2026-10-10", selbst=1, heim="FC Zwei")

        ergebnis = auswerten(user["id"])

        assert ergebnis["saison"] == "26/27"
        assert ergebnis["spiele"] == 2
        assert ergebnis["spesen"] == 50.0
        assert ergebnis["rollen"] == [{"rolle": "SR", "spiele": 1, "spesen": 30.0},
                                      {"rolle": "SRA 1", "spiele": 1, "spesen": 20.0}]
        assert [m["monat"] for m in ergebnis["monate"]] == ["2026-09", "2026-10"]

    def test_eigene_rolle_ueber_den_namen_aus_den_stammdaten(self, user, dienste):
        upsert_stammdaten(user["id"], {"name_vorname": "Fahne, Max"})
        anlegen(user["id"], "2026-09-05")

        ergebnis = auswerten(user["id"])

        assert ergebnis["rollen"] == [{"rolle": "SRA 1", "spiele": 1, "spesen": 20.0}]
        assert ergebnis["ohne_rolle"] == 0

    def test_ohne_erkennbare_rolle(self, user, dienste):
        anlegen(user["id"], "2026-09-05")

        ergebnis = auswerten(user["id"])

        assert (ergebnis["spiele"], ergebnis["ohne_rolle"], ergebnis["spesen"]) == (0, 1, 0)

    def test_nur_vergangene_und_angesetzte_spiele(self, user, dienste):
        anlegen(user["id"], "2026-09-05", selbst=0)
        anlegen(user["id"], "2026-11-24", selbst=0, heim="FC Heute")
        anlegen(user["id"], "2026-12-05", selbst=0, heim="FC Zukunft")
        zurueckgezogen = anlegen(user["id"], "2026-10-01", selbst=0, heim="FC Weg")
        from db.database import get_connection
        conn = get_connection()
        conn.execute("UPDATE matches SET missing_since = '2026-10-02' WHERE id = ?", (zurueckgezogen,))
        conn.commit()
        conn.close()

        assert auswerten(user["id"])["spiele"] == 1

    def test_saisons_und_auswahl(self, user, dienste):
        anlegen(user["id"], "2026-09-05", selbst=0)
        anlegen(user["id"], "2026-03-01", selbst=0, heim="FC Alt")

        assert auswerten(user["id"])["saisons"] == ["26/27", "25/26"]
        assert auswerten(user["id"], "25/26")["monate"][0]["monat"] == "2026-03"
        # Unbekannte Saison: die neueste
        assert auswerten(user["id"], "99/00")["saison"] == "26/27"

    def test_ohne_satz(self, user, dienste):
        anlegen(user["id"], "2026-09-05", selbst=0, sr=None)
        ergebnis = auswerten(user["id"])
        assert (ergebnis["ohne_satz"], ergebnis["spesen"]) == (1, 0)

    def test_ohne_spiele(self, user, dienste):
        ergebnis = auswerten(user["id"])
        assert (ergebnis["saisons"], ergebnis["saison"], ergebnis["spiele"], ergebnis["monate"]) == ([], None, 0, [])
        assert ergebnis["gesamt"] == 0


class TestFahrtkosten:
    def test_erfasste_kilometer_und_oevm(self, user, dienste):
        mid = anlegen(user["id"], "2026-09-05", selbst=0)
        set_official_expenses(mid, {"sr_km": 40, "sr_oevm": 2.5})

        fahrt = auswerten(user["id"])["fahrtkosten"]

        assert (fahrt["erfasst"], fahrt["erfasst_spiele"], fahrt["geschaetzt_spiele"]) == (14.5, 1, 0)
        # Erfasstes wird nicht geschaetzt
        assert dienste == []

    def test_eingetragene_null_zaehlt_als_erfasst(self, user, dienste):
        mid = anlegen(user["id"], "2026-09-05", selbst=1)
        set_official_expenses(mid, {"sra1_km": 0})

        fahrt = auswerten(user["id"])["fahrtkosten"]
        assert (fahrt["erfasst"], fahrt["erfasst_spiele"], fahrt["geschaetzt_spiele"]) == (0, 1, 0)

    def test_schaetzt_hin_und_zurueck_vom_eigenen_wohnort(self, user, dienste):
        anlegen(user["id"], "2026-09-05", selbst=1)   # Weg 2: 22,2 km vom Platz
        anlegen(user["id"], "2026-09-12", selbst=1, heim="FC Zwei")

        ergebnis = auswerten(user["id"])
        fahrt = ergebnis["fahrtkosten"]

        assert fahrt["geschaetzt_spiele"] == 2
        assert fahrt["geschaetzt_km"] == 2 * 44
        assert fahrt["geschaetzt"] == pytest.approx(2 * 44 * 0.30)
        assert ergebnis["monate"][0]["fahrt_geschaetzt"] == pytest.approx(26.4)
        assert ergebnis["gesamt"] == pytest.approx(40 + 26.4)
        # Ein Wohnort, ein Platz: je eine Abfrage hin und zurueck
        assert dienste == [([(50.2, 11.0)], [(50.0, 11.0)]), ([(50.0, 11.0)], [(50.2, 11.0)])]

    def test_dfbnet_koordinate_des_platzes_hat_vorrang(self, user, dienste):
        daten = spiel(tag="2026-09-05")
        daten["schiedsrichter"][0]["selbst"] = True
        daten["spielstaette"].update(lat=50.5, lon=11.0)
        upsert_match(user["id"], daten, "2026-09-05", 30.0, 20.0, 0.30)

        assert auswerten(user["id"])["fahrtkosten"]["geschaetzt_km"] == 89

    def test_ohne_anschrift_keine_schaetzung(self, user, dienste):
        anlegen(user["id"], "2026-09-05", selbst=0, adresse="Unbekannt 9, 11111 Nirgends")

        fahrt = auswerten(user["id"])["fahrtkosten"]
        assert (fahrt["ohne_schaetzung"], fahrt["geschaetzt_spiele"]) == (1, 0)

    def test_luftlinie_ohne_routenplaner(self, user, dienste, monkeypatch):
        def kaputt(*a, **kw):
            raise RoutingNichtErreichbar("weg")
        monkeypatch.setattr(modul, "entfernungen", kaputt)
        anlegen(user["id"], "2026-09-05", selbst=0)

        fahrt = auswerten(user["id"])["fahrtkosten"]
        assert fahrt["luftlinie_spiele"] == 1
        assert fahrt["geschaetzt_km"] == pytest.approx(29, abs=1)

    def test_nicht_nachgeschlagene_strecke_ist_offen(self, user, dienste, monkeypatch):
        monkeypatch.setattr(modul, "entfernungen",
                            lambda q, z, frist=None: Entfernungen([[None] * len(z) for _ in q], len(q) * len(z)))
        anlegen(user["id"], "2026-09-05", selbst=0)

        ergebnis = auswerten(user["id"])
        assert ergebnis["offen"] == 1
        assert ergebnis["fahrtkosten"]["geschaetzt_spiele"] == 0


class TestOrtsuche:
    def test_fragt_nach_der_frist_nicht_mehr(self, monkeypatch):
        gefragt = []
        monkeypatch.setattr(eigene_spiele, "geocode_bekannt", lambda a, o=None: (None, True))
        monkeypatch.setattr(eigene_spiele, "geocode", lambda a, o=None: gefragt.append(a))

        suche = eigene_spiele.Ortsuche(frist=0.0)
        assert suche.punkt("Weg 1, 99999 Irgendwo") is None
        assert suche.punkt("Weg 1, 99999 Irgendwo") is None
        assert (suche.offen, gefragt) == (1, [])

    def test_fragt_vor_der_frist(self, monkeypatch):
        monkeypatch.setattr(eigene_spiele, "geocode_bekannt", lambda a, o=None: (None, True))
        monkeypatch.setattr(eigene_spiele, "geocode", lambda a, o=None: {"lat": 1.0, "lon": 2.0})

        assert eigene_spiele.Ortsuche(frist=float("inf")).punkt("x") == (1.0, 2.0)

    def test_stoerung_beendet_das_fragen(self, monkeypatch):
        from utils.geocoder import GeocoderNichtErreichbar
        aufrufe = []

        def kaputt(a, o=None):
            aufrufe.append(a)
            raise GeocoderNichtErreichbar("weg")
        monkeypatch.setattr(eigene_spiele, "geocode_bekannt", lambda a, o=None: (None, True))
        monkeypatch.setattr(eigene_spiele, "geocode", kaputt)

        suche = eigene_spiele.Ortsuche(frist=float("inf"))
        suche.punkt("a")
        suche.punkt("b")
        assert (aufrufe, suche.offen, suche.gestoert) == (["a"], 2, True)


class TestEigenePerson:
    def test_namensgleichheit_mehrfach_bleibt_offen(self):
        match = {"schiedsrichter": [{"rolle": "SR", "name": "Max Muster"}, {"rolle": "SRA 1", "name": "Max Muster"}]}
        assert eigene_spiele.eigene_person(match, "Muster, Max") is None

    def test_turnier_mit_zweitem_sr(self):
        match = {"schiedsrichter": [{"rolle": "SR", "name": "A Eins"}, {"rolle": "SR", "name": "B Zwei"}],
                 "selbst": {"rolle": "SR", "seq": 1}}
        assert eigene_spiele.eigene_person(match)["name"] == "B Zwei"
