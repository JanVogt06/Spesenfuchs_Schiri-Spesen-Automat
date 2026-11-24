"""
Mileage suggestions: the planner works on a table of distances, the glue to
address lookup and route planner runs against stand-ins.
"""
import pytest

from utils import fahrten
from utils.fahrten import planen, treffpunkt_kandidaten, vorschlaege_fuer_spiel
from utils.geocoder import GeocoderNichtErreichbar
from utils.routing import Entfernungen, RoutingNichtErreichbar


def tabelle(wege):
    """weg(i, j) from a dict of symmetric distances in km; 0 = venue."""
    def weg(i, j):
        if i == j:
            return 0.0
        km = wege.get((i, j), wege.get((j, i)))
        return None if km is None else km * 1000
    return weg


def abholung(fahrer, mitfahrer, km):
    return {"fahrer": fahrer, "mitfahrer": mitfahrer, "km": km, "treffpunkt": None}


class TestPlanen:
    def test_jeder_allein_hin_und_zurueck(self):
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 20, (2, 0): 15, (1, 2): 40}))

        assert ergebnis["einzeln"] == {"km": {"sr": 40, "sra1": 30}, "gesamt": 70}

    def test_nachbarn_fahren_zusammen(self):
        # SR and SRA 1 live 2 km apart, both 20 km from the venue
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 20, (2, 0): 20, (1, 2): 2}))

        vorschlag = ergebnis["fahrgemeinschaften"][0]
        assert vorschlag["km"] == {"sr": 44, "sra1": 0}
        assert vorschlag["fahrten"] == [abholung("sr", ["sra1"], 44)]
        assert vorschlag["ersparnis"] == 80 - 44

    def test_der_guenstigere_faehrt(self):
        # SRA 1 lives on the way: SR picks them up, not the other way round
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 30, (2, 0): 10, (1, 2): 20}))

        assert ergebnis["fahrgemeinschaften"][0]["fahrten"][0]["fahrer"] == "sr"
        assert ergebnis["fahrgemeinschaften"][0]["km"] == {"sr": 60, "sra1": 0}

    def test_abholreihenfolge_und_teilgruppen(self):
        # sra2 lives far away in the other direction
        wege = {(1, 0): 20, (2, 0): 18, (3, 0): 25, (1, 2): 3, (1, 3): 45, (2, 3): 43}
        ergebnis = planen(["sr", "sra1", "sra2"], tabelle(wege))

        bester = ergebnis["fahrgemeinschaften"][0]
        assert bester["fahrten"] == [abholung("sr", ["sra1"], 42), abholung("sra2", [], 50)]
        assert bester["km"] == {"sr": 42, "sra1": 0, "sra2": 50}
        assert all(v["ersparnis"] > 0 for v in ergebnis["fahrgemeinschaften"])
        assert len(ergebnis["fahrgemeinschaften"]) <= fahrten.MAX_VORSCHLAEGE

    def test_keine_fahrgemeinschaft_ohne_ersparnis(self):
        # Opposite directions: picking up costs more than it saves
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 10, (2, 0): 10, (1, 2): 20}))
        assert ergebnis["fahrgemeinschaften"] == []

    def test_unbekannter_weg(self):
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 10, (1, 2): 1}))

        assert ergebnis["einzeln"]["km"] == {"sr": 20}
        assert ergebnis["fahrgemeinschaften"] == []

    def test_rundet_kaufmaennisch(self):
        assert planen(["sr"], tabelle({(1, 0): 10.25}))["einzeln"]["km"] == {"sr": 21}

    def test_teilungen(self):
        assert len(fahrten._teilungen([1, 2, 3])) == 5
        assert fahrten._teilungen([]) == [[]]


class TestTreffpunkt:
    # SR lives 30 km from the venue. SRA 1 lives 8 km off SR's way, next to
    # point 3 on it (2 km away), which is 18 km before the venue. Picking SRA 1
    # up at home means a detour; meeting at point 3 does not.
    WEGE = {(1, 0): 30, (2, 0): 20, (1, 2): 18, (1, 3): 12, (3, 0): 18, (2, 3): 2}

    def test_treffen_unterwegs_schlaegt_abholen(self):
        ergebnis = planen(["sr", "sra1"], tabelle(self.WEGE), {1: [3], 2: []})

        bester = ergebnis["fahrgemeinschaften"][0]
        assert bester["fahrten"] == [{"fahrer": "sr", "mitfahrer": ["sra1"], "km": 60,
                                      "treffpunkt": 3, "zubringer": {"sra1": 4}}]
        # Everyone claims what they drove: the meeting point costs SRA 1 4 km
        assert bester["km"] == {"sr": 60, "sra1": 4}
        assert bester["gesamt"] == 64
        # The pure pick-up is still offered as an alternative
        assert {"sr": 76, "sra1": 0} in [v["km"] for v in ergebnis["fahrgemeinschaften"]]

    def test_treffpunkt_auch_wenn_abholen_kuerzer_ist(self):
        # Consistent distances: picking up wins on kilometres, the meeting
        # point (no detour for the driver) is still offered as an option
        wege = {(1, 0): 30, (2, 0): 25, (1, 2): 8, (1, 3): 10, (3, 0): 20, (2, 3): 6}
        ergebnis = planen(["sr", "sra1"], tabelle(wege), {1: [3]})

        assert [v["gesamt"] for v in ergebnis["fahrgemeinschaften"]] == [66, 72]
        treffen = ergebnis["fahrgemeinschaften"][1]
        assert treffen["fahrten"][0]["treffpunkt"] == 3
        assert treffen["km"] == {"sr": 60, "sra1": 12}

    def test_hoechstens_drei_mit_einem_treffpunkt(self):
        wege = {(1, 0): 20, (2, 0): 21, (3, 0): 22, (1, 2): 2, (1, 3): 3, (2, 3): 2,
                (1, 4): 10, (4, 0): 10, (2, 4): 11, (3, 4): 12}
        ergebnis = planen(["sr", "sra1", "sra2"], tabelle(wege), {1: [4], 2: [], 3: []})

        vorschlaege = ergebnis["fahrgemeinschaften"]
        assert len(vorschlaege) == fahrten.MAX_VORSCHLAEGE
        assert sum(1 for v in vorschlaege if any(f["treffpunkt"] for f in v["fahrten"])) == 1

    def test_unbekannte_strecke_zum_treffpunkt_faellt_weg(self):
        wege = {k: v for k, v in self.WEGE.items() if k != (2, 3)}
        ergebnis = planen(["sr", "sra1"], tabelle(wege), {1: [3]})

        assert all(f["treffpunkt"] != 3 for v in ergebnis["fahrgemeinschaften"] for f in v["fahrten"])

    def test_kandidaten_auf_der_luftlinie(self):
        # About 33 km: eight points, evenly spread, without the end points
        punkte = treffpunkt_kandidaten((50.9, 11.6), (50.6, 11.6))
        assert len(punkte) == 8
        assert all(50.6 < lat < 50.9 for lat, _ in punkte)
        assert punkte == sorted(punkte, reverse=True)

    def test_kandidaten_begrenzt_und_mindestens_einer(self):
        assert len(treffpunkt_kandidaten((50.0, 11.0), (52.0, 11.0))) == fahrten.MAX_TREFFPUNKTE_JE_FAHRER
        assert len(treffpunkt_kandidaten((50.0, 11.0), (50.01, 11.0))) == 1


def _spiel(**kw):
    return {
        "staette_lat": 50.0, "staette_lon": 11.0,
        "spielstaette": {"name": "Platz", "adresse": "Platzweg, 99999 Ort"},
        "schiedsrichter": [
            {"rolle": "SR", "name": "Erika Pfeife", "strasse": "Weg 1", "plz_ort": "99999 Ort"},
            {"rolle": "SRA 1", "name": "Max Fahne", "strasse": "", "plz_ort": "99998 Dorf"},
            {"rolle": "SRA 2", "name": "Moritz Fahne", "strasse": "Weg 3", "plz_ort": ""},
        ],
        "selbst": {"rolle": "SRA 1", "seq": 0},
        **kw,
    }


@pytest.fixture
def dienste(monkeypatch):
    geocodiert, namen = [], []
    adressen = {"Weg 1, 99999 Ort": (50.1, 11.0), "99998 Dorf": (50.2, 11.0), "Platzweg, 99999 Ort": (50.0, 11.0)}

    def geocode(adresse, ort=None):
        geocodiert.append(adresse)
        if isinstance(adressen.get(adresse), Exception):
            raise adressen[adresse]
        punkt = adressen.get(adresse)
        return {"lat": punkt[0], "lon": punkt[1], "genauigkeit": "adresse"} if punkt else None

    def entfernungen(quellen, ziele, frist=None):
        # 11.1 km per 0.1 degree of latitude
        return Entfernungen([[abs(q[0] - z[0]) * 111_000 for z in ziele] for q in quellen], 0)

    monkeypatch.setattr(fahrten, "geocode", geocode)
    monkeypatch.setattr(fahrten, "entfernungen", entfernungen)
    monkeypatch.setattr(fahrten, "ortsname", lambda lat, lon: namen.append((lat, lon)) or "Mitteldorf")
    return geocodiert, adressen, namen


class TestVorschlaegeFuerSpiel:
    def test_mit_dfbnet_koordinate_und_gefundenen_anschriften(self, dienste):
        geocodiert, _, _ = dienste

        antwort = vorschlaege_fuer_spiel(_spiel())

        # DFBnet knows the venue; a person without a place is not even looked up
        assert geocodiert == ["Weg 1, 99999 Ort", "99998 Dorf"]
        assert antwort["quelle"] == "strasse"
        assert antwort["selbst"] == "sra1"
        assert antwort["ohne_anschrift"] == ["SRA 2"]
        assert antwort["einzeln"]["km"] == {"sr": 22, "sra1": 44}
        # Everyone lives on one line: SRA 1 picks SR up on the way
        assert antwort["fahrgemeinschaften"][0]["fahrten"] == [abholung("sra1", ["sr"], 44)]

    def test_treffpunkt_bekommt_koordinate_und_ortsnamen(self, dienste, monkeypatch):
        _, adressen, namen = dienste
        # SR now lives off to the side of SRA 1's way: a meeting point is offered
        adressen["Weg 1, 99999 Ort"] = (50.1, 11.05)

        def entfernungen(quellen, ziele, frist=None):
            return Entfernungen([[((q[0] - z[0]) ** 2 + ((q[1] - z[1]) * 0.6) ** 2) ** 0.5 * 111_000
                                  for z in ziele] for q in quellen], 0)
        monkeypatch.setattr(fahrten, "entfernungen", entfernungen)
        antwort = vorschlaege_fuer_spiel(_spiel())

        treffen = [f for v in antwort["fahrgemeinschaften"] for f in v["fahrten"] if f["treffpunkt"]]
        assert treffen, antwort["fahrgemeinschaften"]
        assert treffen[0]["treffpunkt"]["name"] == "Mitteldorf"
        assert treffen[0]["treffpunkt"]["lat"] is not None
        assert namen

    def test_spielort_ueber_die_adresse(self, dienste):
        geocodiert, _, _ = dienste
        antwort = vorschlaege_fuer_spiel(_spiel(staette_lat=None, staette_lon=None))

        assert geocodiert[0] == "Platzweg, 99999 Ort"
        assert antwort["einzeln"]["km"]["sr"] == 22

    def test_ohne_spielort(self, dienste):
        antwort = vorschlaege_fuer_spiel(_spiel(staette_lat=None, spielstaette={"adresse": ""}))
        assert antwort["ohne_spielort"] is True
        assert antwort["einzeln"]["km"] == {}

    def test_luftlinie_wenn_der_routenplaner_ausfaellt(self, dienste, monkeypatch):
        def kaputt(*a, **kw):
            raise RoutingNichtErreichbar("weg")
        monkeypatch.setattr(fahrten, "entfernungen", kaputt)

        antwort = vorschlaege_fuer_spiel(_spiel())

        assert antwort["quelle"] == "luftlinie"
        # 11.1 km straight line x 1.3, there and back
        assert antwort["einzeln"]["km"]["sr"] == pytest.approx(29, abs=1)

    def test_adresssuche_gestoert(self, dienste):
        _, adressen, _ = dienste
        adressen["99998 Dorf"] = GeocoderNichtErreichbar("weg")

        antwort = vorschlaege_fuer_spiel(_spiel())

        assert antwort["quelle"] == "gestoert"
        assert antwort["einzeln"]["km"] == {}

    def test_ohne_personen(self, dienste):
        antwort = vorschlaege_fuer_spiel(_spiel(schiedsrichter=[]))
        assert antwort["einzeln"] == {"km": {}, "gesamt": 0}
        assert antwort["selbst"] == "sra1"

    def test_allein_keine_treffpunkte(self, dienste):
        _, _, namen = dienste
        antwort = vorschlaege_fuer_spiel(_spiel(schiedsrichter=_spiel()["schiedsrichter"][:1]))
        assert antwort["fahrgemeinschaften"] == []
        assert namen == []
