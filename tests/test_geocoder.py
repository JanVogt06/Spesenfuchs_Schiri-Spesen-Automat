"""
Geocoder ohne Netz: urlopen ist durch eine Attrappe ersetzt, die Uhr fuer
den Mindestabstand ebenso. Der Zwischenspeicher laeuft gegen die echte
(Wegwerf-)Datenbank aus der db-Fixture.
"""
import json
from datetime import datetime, timedelta, UTC
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from db.geocode import get_cached, store
from utils import geocoder
from utils.geocoder import (
    MISS_GUELTIG_TAGE,
    STANDARD_URL,
    USER_AGENT,
    GeocoderNichtErreichbar,
    geocode,
)


class FalscherDienst:
    """Ersatz fuer urlopen: liefert vorbereitete Antworten der Reihe nach."""

    def __init__(self):
        self.antworten = {}
        self.standard = []
        self.anfragen = []

    def antwort(self, anfrage_text, ergebnis):
        """Antwort fuer eine bestimmte q-Anfrage (Liste, Ausnahme oder bytes)."""
        self.antworten[anfrage_text] = ergebnis

    def __call__(self, request, timeout=None):
        self.anfragen.append(SimpleNamespace(request=request, timeout=timeout))
        q = parse_qs(urlparse(request.full_url).query)["q"][0]
        ergebnis = self.antworten.get(q, self.standard)
        if isinstance(ergebnis, BaseException):
            raise ergebnis
        rohdaten = ergebnis if isinstance(ergebnis, bytes) else json.dumps(ergebnis).encode()
        return _Antwort(rohdaten)

    @property
    def gefragt(self):
        return [parse_qs(urlparse(a.request.full_url).query)["q"][0] for a in self.anfragen]


class _Antwort:
    def __init__(self, rohdaten):
        self._rohdaten = rohdaten

    def read(self):
        return self._rohdaten

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _treffer(lat, lon, plz=None):
    eintrag = {"lat": str(lat), "lon": str(lon)}
    if plz:
        eintrag["address"] = {"postcode": plz}
    return [eintrag]


@pytest.fixture
def dienst(db, monkeypatch):
    """Frische Datenbank, Attrappe statt Netz, kein Mindestabstand."""
    falsch = FalscherDienst()
    monkeypatch.setattr(geocoder, "urlopen", falsch)
    monkeypatch.setattr(geocoder, "_letzte_anfrage", 0.0)
    monkeypatch.setenv("GEOCODER_MIN_INTERVAL", "0")
    monkeypatch.delenv("NOMINATIM_URL", raising=False)
    return falsch


# ===== Einstellungen =====

class TestEinstellungen:
    def test_standard_url(self, monkeypatch):
        monkeypatch.delenv("NOMINATIM_URL", raising=False)
        assert geocoder.basis_url() == STANDARD_URL

    def test_eigene_url_ohne_schraegstrich(self, monkeypatch):
        monkeypatch.setenv("NOMINATIM_URL", "http://nominatim.lan:8080/")
        assert geocoder.basis_url() == "http://nominatim.lan:8080"

    @pytest.mark.parametrize("wert, erwartet", [
        (None, 1.0), ("0.25", 0.25), ("0", 0.0), ("-5", 0.0), ("schnell", 1.0),
    ])
    def test_min_intervall(self, monkeypatch, wert, erwartet):
        if wert is None:
            monkeypatch.delenv("GEOCODER_MIN_INTERVAL", raising=False)
        else:
            monkeypatch.setenv("GEOCODER_MIN_INTERVAL", wert)
        assert geocoder._min_intervall() == erwartet

    def test_normalisieren(self):
        assert geocoder._normalisieren("  Hauptstr.  1,\n 99084   Erfurt , ") == "hauptstr. 1, 99084 erfurt"

    @pytest.mark.parametrize("adresse, ort", [
        ("Karl-Liebknecht-Str., 07806 Neustadt an der Orla", "07806 Neustadt an der Orla"),
        ("Hauptstr. 1 99084 Erfurt", "99084 Erfurt"),
        ("Irgendwo", None),
    ])
    def test_ort_aus_adresse(self, adresse, ort):
        assert geocoder._ort_aus_adresse(adresse) == ort


# ===== Anfrage =====

class TestAnfrage:
    def test_treffer(self, dienst):
        dienst.standard = _treffer(50.97, 11.03)
        assert geocode("Hauptstr. 1, 99084 Erfurt") == {"lat": 50.97, "lon": 11.03, "genauigkeit": "adresse"}

    def test_parameter_und_kopfzeilen(self, dienst):
        dienst.standard = _treffer(50.97, 11.03)
        geocode("Hauptstr. 1, 99084 Erfurt")

        anfrage = dienst.anfragen[0]
        url = urlparse(anfrage.request.full_url)
        assert f"{url.scheme}://{url.netloc}" == STANDARD_URL
        assert url.path == "/search"
        parameter = {k: v[0] for k, v in parse_qs(url.query).items()}
        assert parameter == {
            "q": "hauptstr. 1, 99084 erfurt",
            "format": "jsonv2",
            "limit": "1",
            "countrycodes": "de",
            "addressdetails": "1",
        }
        assert anfrage.request.get_header("User-agent") == USER_AGENT
        assert anfrage.request.get_header("Accept-language") == "de"
        assert anfrage.timeout == geocoder.TIMEOUT_SEKUNDEN

    def test_eigener_dienst(self, dienst, monkeypatch):
        monkeypatch.setenv("NOMINATIM_URL", "http://nominatim.lan:8080/")
        dienst.standard = _treffer(1, 2)
        geocode("Hauptstr. 1, 99084 Erfurt")
        assert dienst.anfragen[0].request.full_url.startswith("http://nominatim.lan:8080/search?")

    def test_leere_adresse_ohne_anfrage(self, dienst):
        assert geocode("   ") is None
        assert geocode(" , ") is None
        assert dienst.anfragen == []

    def test_unbekannt_faellt_auf_ort_zurueck(self, dienst):
        dienst.antwort("karl-liebknecht-str., 07806 neustadt an der orla", [])
        dienst.antwort("07806 neustadt an der orla", _treffer(50.73, 11.75, "07806"))
        assert geocode("Karl-Liebknecht-Str., 07806 Neustadt an der Orla") == {
            "lat": 50.73, "lon": 11.75, "genauigkeit": "ort",
        }
        assert dienst.gefragt == [
            "karl-liebknecht-str., 07806 neustadt an der orla",
            "07806 neustadt an der orla",
        ]

    def test_ort_vom_aufrufer(self, dienst):
        dienst.antwort("hauptstr. 1", [])
        dienst.antwort("99438 bad berka", _treffer(50.9, 11.3))
        assert geocode("Hauptstr. 1", ort="99438 Bad Berka")["genauigkeit"] == "ort"

    def test_ort_gleich_adresse_nur_eine_anfrage(self, dienst):
        dienst.standard = []
        assert geocode("99084 Erfurt", ort="99084  erfurt") is None
        assert len(dienst.anfragen) == 1

    def test_ganz_unbekannt(self, dienst):
        dienst.standard = []
        assert geocode("Gibtsnicht 1, 99999 Nirgendwo") is None

    def test_postleitzahl_widerspricht(self, dienst):
        # Nominatim raet lieber, als nichts zu liefern
        dienst.standard = _treffer(53.55, 9.99, "20095")
        assert geocode("Erfundene Str. 1, 99084 Erfurt") is None

    def test_postleitzahl_nachbarbezirk_gilt(self, dienst):
        dienst.standard = _treffer(50.97, 11.03, "99085")
        assert geocode("Hauptstr. 1, 99084 Erfurt")["genauigkeit"] == "adresse"

    def test_treffer_ohne_postleitzahl_gilt(self, dienst):
        dienst.standard = _treffer(50.97, 11.03)
        assert geocode("Hauptstr. 1, 99084 Erfurt") is not None

    def test_kaputte_koordinate(self, dienst):
        dienst.standard = [{"lat": "abc", "lon": "11"}]
        assert geocoder._abfragen("irgendwo") is None

    def test_treffer_ohne_koordinate(self, dienst):
        dienst.standard = [{"display_name": "x"}]
        assert geocoder._abfragen("irgendwo") is None


# ===== Nicht erreichbar =====

class TestNichtErreichbar:
    @pytest.mark.parametrize("fehler", [
        URLError("Name or service not known"),
        HTTPError("http://x", 503, "Service Unavailable", {}, None),
        TimeoutError("timed out"),
        ConnectionResetError("reset"),
    ])
    def test_wird_zu_eigener_ausnahme(self, dienst, fehler):
        dienst.standard = fehler
        with pytest.raises(GeocoderNichtErreichbar):
            geocode("Hauptstr. 1, 99084 Erfurt")

    def test_kein_json(self, dienst):
        dienst.standard = b"<html>Wartung</html>"
        with pytest.raises(GeocoderNichtErreichbar):
            geocode("Hauptstr. 1, 99084 Erfurt")

    def test_ausfall_landet_nicht_im_speicher(self, dienst):
        dienst.standard = URLError("weg")
        with pytest.raises(GeocoderNichtErreichbar):
            geocode("Hauptstr. 1, 99084 Erfurt")
        assert get_cached("hauptstr. 1, 99084 erfurt", STANDARD_URL) is None

        # Sobald der Dienst wieder da ist, wird gefragt
        dienst.standard = _treffer(50.97, 11.03)
        assert geocode("Hauptstr. 1, 99084 Erfurt") is not None


# ===== Zwischenspeicher =====

class TestZwischenspeicher:
    def test_treffer_wird_gespeichert(self, dienst):
        dienst.standard = _treffer(50.97, 11.03)
        geocode("Hauptstr. 1, 99084 Erfurt")
        eintrag = get_cached("hauptstr. 1, 99084 erfurt", STANDARD_URL)
        assert (eintrag["lat"], eintrag["lon"]) == (50.97, 11.03)

    def test_zweiter_aufruf_ohne_anfrage(self, dienst):
        dienst.standard = _treffer(50.97, 11.03)
        erstes = geocode("Hauptstr. 1, 99084 Erfurt")
        zweites = geocode("  HAUPTSTR. 1,   99084 erfurt ")
        assert erstes == zweites
        assert len(dienst.anfragen) == 1

    def test_fehlschlag_wird_gespeichert_und_nicht_wiederholt(self, dienst):
        dienst.standard = []
        assert geocoder._nachschlagen("Gibtsnicht 1") is None
        assert geocoder._nachschlagen("Gibtsnicht 1") is None
        assert len(dienst.anfragen) == 1
        eintrag = get_cached("gibtsnicht 1", STANDARD_URL)
        assert eintrag["lat"] is None and eintrag["lon"] is None

    def test_alter_fehlschlag_wird_neu_versucht(self, dienst):
        alt = (datetime.now(UTC) - timedelta(days=MISS_GUELTIG_TAGE + 1)).isoformat()
        store("gibtsnicht 1", STANDARD_URL, None, None)
        from db.database import get_connection
        conn = get_connection()
        conn.execute("UPDATE geocode_cache SET resolved_at = ?", (alt,))
        conn.commit()
        conn.close()

        dienst.standard = _treffer(1.5, 2.5)
        assert geocoder._nachschlagen("Gibtsnicht 1") == (1.5, 2.5)
        assert len(dienst.anfragen) == 1
        assert get_cached("gibtsnicht 1", STANDARD_URL)["lat"] == 1.5

    def test_vorhandener_treffer_aus_dem_speicher(self, dienst):
        store("hauptstr. 1", STANDARD_URL, 10.0, 20.0)
        assert geocoder._nachschlagen("Hauptstr. 1") == (10.0, 20.0)
        assert dienst.anfragen == []

    def test_getrennter_speicher_je_dienst(self, dienst, monkeypatch):
        dienst.standard = _treffer(1.0, 1.0)
        geocode("Hauptstr. 1")

        monkeypatch.setenv("NOMINATIM_URL", "http://nominatim.lan")
        dienst.standard = _treffer(2.0, 2.0)
        assert geocode("Hauptstr. 1")["lat"] == 2.0
        assert len(dienst.anfragen) == 2

        assert get_cached("hauptstr. 1", STANDARD_URL)["lat"] == 1.0
        assert get_cached("hauptstr. 1", "http://nominatim.lan")["lat"] == 2.0

        # Zurueck zum Standard: wieder aus dem Speicher, ohne Anfrage
        monkeypatch.delenv("NOMINATIM_URL")
        assert geocode("Hauptstr. 1")["lat"] == 1.0
        assert len(dienst.anfragen) == 2

    def test_fehlschlag_bei_einem_dienst_gilt_nicht_fuer_den_anderen(self, dienst, monkeypatch):
        dienst.standard = []
        geocoder._nachschlagen("Hauptstr. 1")
        monkeypatch.setenv("NOMINATIM_URL", "http://nominatim.lan/")
        dienst.standard = _treffer(3.0, 4.0)
        assert geocoder._nachschlagen("Hauptstr. 1") == (3.0, 4.0)

    @pytest.mark.parametrize("resolved_at, abgelaufen", [
        ((datetime.now(UTC) - timedelta(days=MISS_GUELTIG_TAGE + 1)).isoformat(), True),
        ((datetime.now(UTC) - timedelta(days=1)).isoformat(), False),
        # Ohne Zeitzone gilt UTC
        ((datetime.now(UTC) - timedelta(days=MISS_GUELTIG_TAGE + 1)).replace(tzinfo=None).isoformat(), True),
        (datetime.now(UTC).replace(tzinfo=None).isoformat(), False),
        ("kein datum", True),
    ])
    def test_fehlschlag_abgelaufen(self, resolved_at, abgelaufen):
        assert geocoder._fehlschlag_abgelaufen(resolved_at) is abgelaufen


# ===== Mindestabstand =====

class FalscheUhr:
    def __init__(self, start=1000.0):
        self.jetzt = start
        self.geschlafen = []

    def monotonic(self):
        return self.jetzt

    def sleep(self, sekunden):
        self.geschlafen.append(sekunden)
        self.jetzt += sekunden


@pytest.fixture
def uhr(dienst, monkeypatch):
    falsch = FalscheUhr()
    monkeypatch.setattr(geocoder, "time", SimpleNamespace(monotonic=falsch.monotonic, sleep=falsch.sleep))
    monkeypatch.setenv("GEOCODER_MIN_INTERVAL", "1.0")
    dienst.standard = _treffer(1, 2)
    return falsch


class TestMindestabstand:
    def test_erste_anfrage_wartet_nicht(self, uhr):
        geocoder._abfragen("a")
        assert uhr.geschlafen == []

    def test_direkt_danach_wird_gewartet(self, uhr):
        geocoder._abfragen("a")
        uhr.jetzt += 0.25
        geocoder._abfragen("b")
        assert uhr.geschlafen == [pytest.approx(0.75)]

    def test_nach_ablauf_keine_wartezeit(self, uhr):
        geocoder._abfragen("a")
        uhr.jetzt += 1.5
        geocoder._abfragen("b")
        assert uhr.geschlafen == []

    def test_eigenes_intervall(self, uhr, monkeypatch):
        monkeypatch.setenv("GEOCODER_MIN_INTERVAL", "3")
        geocoder._abfragen("a")
        uhr.jetzt += 1
        geocoder._abfragen("b")
        assert uhr.geschlafen == [pytest.approx(2.0)]

    def test_ohne_intervall_nie_warten(self, uhr, monkeypatch):
        monkeypatch.setenv("GEOCODER_MIN_INTERVAL", "0")
        for adresse in "abc":
            geocoder._abfragen(adresse)
        assert uhr.geschlafen == []

    def test_auch_fehlschlag_zaehlt_als_anfrage(self, uhr, dienst):
        dienst.antwort("a", URLError("weg"))
        with pytest.raises(GeocoderNichtErreichbar):
            geocoder._abfragen("a")
        uhr.jetzt += 0.5
        geocoder._abfragen("b")
        assert uhr.geschlafen == [pytest.approx(0.5)]

    def test_zeitpunkt_nach_der_antwort(self, uhr):
        geocoder._abfragen("a")
        assert geocoder._letzte_anfrage == uhr.jetzt

    def test_speichertreffer_wartet_nicht(self, uhr):
        geocode("Hauptstr. 1")
        uhr.jetzt += 0.1
        geocode("Hauptstr. 1")
        assert uhr.geschlafen == []
