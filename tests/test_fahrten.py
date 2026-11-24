"""
Kilometer-Vorschlaege: die Planung rechnet auf einer Wegtabelle, die Anbindung
an Adresssuche und Routenplaner laeuft gegen Attrappen.
"""
import pytest

from utils import fahrten
from utils.fahrten import planen, vorschlaege_fuer_spiel
from utils.geocoder import GeocoderNichtErreichbar
from utils.routing import Entfernungen, RoutingNichtErreichbar


def tabelle(wege):
    """weg(i, j) aus einem Dict symmetrischer Wege in km; 0 = Spielort."""
    def weg(i, j):
        if i == j:
            return 0.0
        km = wege.get((i, j), wege.get((j, i)))
        return None if km is None else km * 1000
    return weg


class TestPlanen:
    def test_jeder_allein_hin_und_zurueck(self):
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 20, (2, 0): 15, (1, 2): 40}))

        assert ergebnis["einzeln"] == {"km": {"sr": 40, "sra1": 30}, "gesamt": 70}

    def test_nachbarn_fahren_zusammen(self):
        # SR und SRA 1 wohnen 2 km auseinander, beide 20 km vom Platz
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 20, (2, 0): 20, (1, 2): 2}))

        (vorschlag,) = ergebnis["fahrgemeinschaften"]
        assert vorschlag["km"] == {"sr": 44, "sra1": 0}
        assert vorschlag["fahrten"] == [{"fahrer": "sr", "mitfahrer": ["sra1"], "km": 44}]
        assert vorschlag["ersparnis"] == 80 - 44

    def test_der_guenstigere_faehrt(self):
        # SRA 1 wohnt auf dem Weg: SR holt ihn ab, nicht umgekehrt
        ergebnis = planen(["sr", "sra1"], tabelle({(1, 0): 30, (2, 0): 10, (1, 2): 20}))

        assert ergebnis["fahrgemeinschaften"][0]["fahrten"][0]["fahrer"] == "sr"
        assert ergebnis["fahrgemeinschaften"][0]["km"] == {"sr": 60, "sra1": 0}

    def test_abholreihenfolge_und_teilgruppen(self):
        # sra2 wohnt weit weg in der anderen Richtung
        wege = {(1, 0): 20, (2, 0): 18, (3, 0): 25, (1, 2): 3, (1, 3): 45, (2, 3): 43}
        ergebnis = planen(["sr", "sra1", "sra2"], tabelle(wege))

        bester = ergebnis["fahrgemeinschaften"][0]
        assert bester["fahrten"] == [
            {"fahrer": "sr", "mitfahrer": ["sra1"], "km": 42},
            {"fahrer": "sra2", "mitfahrer": [], "km": 50},
        ]
        assert bester["km"] == {"sr": 42, "sra1": 0, "sra2": 50}
        assert all(v["ersparnis"] > 0 for v in ergebnis["fahrgemeinschaften"])
        assert len(ergebnis["fahrgemeinschaften"]) <= fahrten.MAX_VORSCHLAEGE

    def test_keine_fahrgemeinschaft_ohne_ersparnis(self):
        # Entgegengesetzte Richtungen: abholen kostet mehr, als es spart
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
    geocodiert = []
    adressen = {"Weg 1, 99999 Ort": (50.1, 11.0), "99998 Dorf": (50.2, 11.0), "Platzweg, 99999 Ort": (50.0, 11.0)}

    def geocode(adresse, ort=None):
        geocodiert.append(adresse)
        if isinstance(adressen.get(adresse), Exception):
            raise adressen[adresse]
        punkt = adressen.get(adresse)
        return {"lat": punkt[0], "lon": punkt[1], "genauigkeit": "adresse"} if punkt else None

    def entfernungen(quellen, ziele, frist=None):
        # 11,1 km je 0,1 Grad Breite
        return Entfernungen([[abs(q[0] - z[0]) * 111_000 for z in ziele] for q in quellen], 0)

    monkeypatch.setattr(fahrten, "geocode", geocode)
    monkeypatch.setattr(fahrten, "entfernungen", entfernungen)
    return geocodiert, adressen


class TestVorschlaegeFuerSpiel:
    def test_mit_dfbnet_koordinate_und_gefundenen_anschriften(self, dienste):
        geocodiert, _ = dienste

        antwort = vorschlaege_fuer_spiel(_spiel())

        # Den Platz kennt DFBnet, eine Person ohne Ort wird gar nicht erst gesucht
        assert geocodiert == ["Weg 1, 99999 Ort", "99998 Dorf"]
        assert antwort["quelle"] == "strasse"
        assert antwort["selbst"] == "sra1"
        assert antwort["ohne_anschrift"] == ["SRA 2"]
        assert antwort["einzeln"]["km"] == {"sr": 22, "sra1": 44}
        assert antwort["fahrgemeinschaften"][0]["fahrten"] == [{"fahrer": "sra1", "mitfahrer": ["sr"], "km": 44}]

    def test_spielort_ueber_die_adresse(self, dienste):
        geocodiert, _ = dienste
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
        # 11,1 km Luftlinie x 1,3, hin und zurueck
        assert antwort["einzeln"]["km"]["sr"] == pytest.approx(29, abs=1)

    def test_adresssuche_gestoert(self, dienste):
        _, adressen = dienste
        adressen["99998 Dorf"] = GeocoderNichtErreichbar("weg")

        antwort = vorschlaege_fuer_spiel(_spiel())

        assert antwort["quelle"] == "gestoert"
        assert antwort["einzeln"]["km"] == {}

    def test_ohne_personen(self, dienste):
        antwort = vorschlaege_fuer_spiel(_spiel(schiedsrichter=[]))
        assert antwort["einzeln"] == {"km": {}, "gesamt": 0}
        assert antwort["selbst"] == "sra1"
