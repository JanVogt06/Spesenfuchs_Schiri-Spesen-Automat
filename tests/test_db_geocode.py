"""Geocode cache: 'never asked' and 'nothing found' must remain distinguishable."""
from db import geocode
from db.geocode import get_cached, store
from db_helpers import feste_uhr


class TestGeocodeCache:
    def test_nie_gefragt_ist_none(self, db):
        assert get_cached("Waldweg 1, Irgendwo", "nominatim") is None

    def test_treffer(self, db, monkeypatch):
        feste_uhr(monkeypatch, geocode)
        store("Waldweg 1, Irgendwo", "nominatim", 50.98, 11.03)
        assert get_cached("Waldweg 1, Irgendwo", "nominatim") == {
            "lat": 50.98, "lon": 11.03, "resolved_at": "2026-11-23T12:00:00+00:00",
        }

    def test_fehlschlag_wird_gemerkt(self, db):
        store("Unbekannt 0", "nominatim", None, None)
        eintrag = get_cached("Unbekannt 0", "nominatim")
        assert eintrag is not None
        assert (eintrag["lat"], eintrag["lon"]) == (None, None)

    def test_erneutes_speichern_ueberschreibt(self, db, monkeypatch):
        uhr = feste_uhr(monkeypatch, geocode)
        store("Adresse", "nominatim", None, None)
        uhr.weiter(days=31)
        store("Adresse", "nominatim", 1.0, 2.0)
        assert get_cached("Adresse", "nominatim") == {
            "lat": 1.0, "lon": 2.0, "resolved_at": "2026-12-24T12:00:00+00:00",
        }

    def test_provider_gehoert_zum_schluessel(self, db):
        store("Adresse", "nominatim", 1.0, 2.0)
        store("Adresse", "eigener", 3.0, 4.0)
        assert get_cached("Adresse", "nominatim")["lat"] == 1.0
        assert get_cached("Adresse", "eigener")["lat"] == 3.0
        assert get_cached("Adresse", "dritter") is None
