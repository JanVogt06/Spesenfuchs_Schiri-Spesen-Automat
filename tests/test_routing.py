"""
Routenplaner ohne Netz: urlopen ist eine Attrappe, die eine Matrix aus einer
Funktion der Koordinaten berechnet. Der Zwischenspeicher laeuft gegen die
Wegwerf-Datenbank der db-Fixture.
"""
import json
from datetime import datetime, timedelta, UTC
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from db.strecken import get_strecken, store_strecken
from utils import routing
from utils.routing import (
    STANDARD_URL,
    RoutingNichtErreichbar,
    entfernungen,
    luftlinie_m,
)

JENA = (50.92721, 11.58640)
WEIMAR = (50.97937, 11.32925)
ERFURT = (50.97870, 11.02890)


class _Antwort:
    def __init__(self, rohdaten):
        self._rohdaten = rohdaten

    def read(self):
        return self._rohdaten

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FalscherPlaner:
    """Antwortet mit 1000 x (Index der Quelle + 1) + Index des Ziels Metern."""

    def __init__(self):
        self.anfragen = []
        self.fehler = None
        self.antwort = None

    def __call__(self, request, timeout=None):
        self.anfragen.append(request)
        if self.fehler:
            raise self.fehler
        url = urlsplit(request.full_url)
        punkte = url.path.rsplit("/", 1)[-1].split(";")
        query = parse_qs(url.query)
        quellen = [int(i) for i in query["sources"][0].split(";")]
        ziele = [int(i) for i in query["destinations"][0].split(";")]
        assert len(punkte) == len(quellen) + len(ziele)
        if self.antwort is not None:
            return _Antwort(json.dumps(self.antwort).encode())
        matrix = [[1000.0 * (q + 1) + z for z in range(len(ziele))] for q in range(len(quellen))]
        return _Antwort(json.dumps({"code": "Ok", "distances": matrix}).encode())


@pytest.fixture
def planer(db, monkeypatch):
    falsch = FalscherPlaner()
    monkeypatch.setattr(routing, "urlopen", falsch)
    monkeypatch.setattr(routing, "_letzte_anfrage", 0.0)
    monkeypatch.setenv("ROUTING_MIN_INTERVAL", "0")
    monkeypatch.delenv("ROUTING_URL", raising=False)
    return falsch


class TestAnfrage:
    def test_eine_anfrage_fuer_die_ganze_matrix(self, planer):
        ergebnis = entfernungen([JENA, WEIMAR], [ERFURT])

        assert len(planer.anfragen) == 1
        url = planer.anfragen[0].full_url
        assert url.startswith(f"{STANDARD_URL}/table/v1/driving/11.58640,50.92720;11.32930,50.97940;11.02890,50.97870?")
        assert "annotations=distance" in url
        assert planer.anfragen[0].get_header("User-agent").startswith("Spesenfuchs/")
        assert ergebnis.meter == [[1000.0], [2000.0]]
        assert ergebnis.offen == 0

    def test_eigener_dienst(self, planer, monkeypatch):
        monkeypatch.setenv("ROUTING_URL", "http://osrm.local:5000/")
        entfernungen([JENA], [WEIMAR])
        assert planer.anfragen[0].full_url.startswith("http://osrm.local:5000/table/v1/driving/")

    def test_gleicher_punkt_ohne_anfrage(self, planer):
        assert entfernungen([JENA], [JENA]).meter == [[0.0]]
        assert planer.anfragen == []

    def test_kein_weg_wird_none(self, planer):
        planer.antwort = {"code": "Ok", "distances": [[None]]}
        assert entfernungen([JENA], [WEIMAR]).meter == [[None]]

    @pytest.mark.parametrize("antwort", [
        {"code": "NoTable"}, {"code": "Ok", "distances": []}, {"code": "Ok", "distances": [[1, 2]]},
    ])
    def test_unerwartete_antwort(self, planer, antwort):
        planer.antwort = antwort
        with pytest.raises(RoutingNichtErreichbar):
            entfernungen([JENA], [WEIMAR])

    def test_ausfall(self, planer):
        planer.fehler = URLError("weg")
        with pytest.raises(RoutingNichtErreichbar):
            entfernungen([JENA], [WEIMAR])
        # Ein Ausfall landet nicht im Speicher
        assert get_strecken([(JENA, WEIMAR)], STANDARD_URL) == {}


class TestZwischenspeicher:
    def test_zweiter_aufruf_ohne_anfrage(self, planer):
        entfernungen([JENA], [WEIMAR, ERFURT])
        planer.anfragen.clear()

        assert entfernungen([JENA], [ERFURT, WEIMAR]).meter == [[1001.0, 1000.0]]
        assert planer.anfragen == []

    def test_rundet_auf_zehn_meter(self, planer):
        entfernungen([JENA], [WEIMAR])
        planer.anfragen.clear()

        assert entfernungen([(50.927214, 11.586398)], [WEIMAR]).meter == [[1000.0]]
        assert planer.anfragen == []

    def test_fragt_nur_was_fehlt(self, planer):
        entfernungen([JENA], [WEIMAR])
        planer.anfragen.clear()

        entfernungen([JENA], [WEIMAR, ERFURT])

        assert len(planer.anfragen) == 1
        assert "11.02890,50.97870" in planer.anfragen[0].full_url
        assert "11.32930,50.97940" not in planer.anfragen[0].full_url

    def test_kein_weg_wird_nicht_gleich_wiederholt(self, planer):
        planer.antwort = {"code": "Ok", "distances": [[None]]}
        entfernungen([JENA], [WEIMAR])
        planer.anfragen.clear()

        assert entfernungen([JENA], [WEIMAR]).meter == [[None]]
        assert planer.anfragen == []

    def test_alter_fehlschlag_wird_neu_gefragt(self, planer, monkeypatch):
        store_strecken([(JENA, WEIMAR, None)], STANDARD_URL)
        monkeypatch.setattr(routing, "_abgelaufen", lambda _: True)

        assert entfernungen([JENA], [WEIMAR]).meter == [[1000.0]]

    def test_richtung_zaehlt(self, planer):
        entfernungen([JENA], [WEIMAR])
        planer.anfragen.clear()

        entfernungen([WEIMAR], [JENA])
        assert len(planer.anfragen) == 1


class TestFrist:
    def test_abgelaufene_frist_fragt_nichts_und_meldet_offen(self, planer):
        ergebnis = entfernungen([JENA], [WEIMAR, ERFURT], frist=0.0)

        assert planer.anfragen == []
        assert ergebnis.meter == [[None, None]]
        assert ergebnis.offen == 2

    def test_gespeichertes_kommt_trotz_frist(self, planer):
        entfernungen([JENA], [WEIMAR])
        ergebnis = entfernungen([JENA], [WEIMAR, ERFURT], frist=0.0)

        assert ergebnis.meter == [[1000.0, None]]
        assert ergebnis.offen == 1


class TestBuendeln:
    def test_viele_ziele_in_mehreren_anfragen(self, planer):
        ziele = [(50.0 + i / 100, 11.0) for i in range(120)]

        ergebnis = entfernungen([JENA], ziele)

        assert len(planer.anfragen) == 3
        assert all(m is not None for m in ergebnis.meter[0])


def test_luftlinie():
    # Jena - Weimar: gut 19 km
    assert 18_500 < luftlinie_m(JENA, WEIMAR) < 19_500
    assert luftlinie_m(JENA, JENA) == 0


def test_abgelaufen():
    assert routing._abgelaufen((datetime.now(UTC) - timedelta(days=31)).isoformat())
    assert not routing._abgelaufen(datetime.now(UTC).isoformat())
    assert routing._abgelaufen("kaputt")


def test_ein_gespann_ist_eine_anfrage(planer):
    punkte = [JENA, WEIMAR, ERFURT, (50.6483, 11.3659)]

    ergebnis = entfernungen(punkte, punkte)

    assert len(planer.anfragen) == 1
    assert all(m is not None for zeile in ergebnis.meter for m in zeile)
    assert [ergebnis.meter[i][i] for i in range(4)] == [0.0] * 4
