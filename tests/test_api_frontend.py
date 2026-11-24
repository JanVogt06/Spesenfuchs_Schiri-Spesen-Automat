"""
Serving the frontend (catch-all), general error handler and CORS.

FRONTEND_DIR points to a non-existent directory in conftest; for the cases
with a frontend it is redirected to a throwaway folder in the API module.
"""
import pytest

from api_hilfen import fehlerbild

INDEX = "<!doctype html><title>Spesenfuchs</title><div id=root></div>"


@pytest.fixture
def frontend(tmp_path, monkeypatch):
    import api.main_api as modul

    wurzel = tmp_path / "dist"
    (wurzel / "unter").mkdir(parents=True)
    (wurzel / "index.html").write_text(INDEX, encoding="utf-8")
    (wurzel / "sw.js").write_text("self.addEventListener('fetch', () => {})", encoding="utf-8")
    (wurzel / "manifest.webmanifest").write_text('{"name": "Spesenfuchs"}', encoding="utf-8")
    (wurzel / "robots.txt").write_text("User-agent: *", encoding="utf-8")
    (wurzel / "appicon.png").write_bytes(b"\x89PNG\r\n\x1a\nicon")
    (wurzel / "unter" / "versteckt.txt").write_text("nur im Unterordner", encoding="utf-8")
    (tmp_path / "geheim.txt").write_text("ausserhalb des Frontends", encoding="utf-8")

    monkeypatch.setattr(modul, "FRONTEND_DIR", wurzel)
    return wurzel


class TestOhneFrontend:
    def test_wurzel_404(self, client, db):
        antwort = client.get("/")
        assert antwort.status_code == 404
        assert antwort.json() == {"detail": "Frontend not available"}

    def test_route_404(self, client, db):
        assert client.get("/einstellungen").status_code == 404

    def test_appicon_404(self, client, db):
        assert client.get("/appicon.png").status_code == 404

    def test_unbekannte_api_404(self, client, db):
        antwort = client.get("/api/gibt-es-nicht")
        assert antwort.status_code == 404
        assert antwort.json() == {"detail": "API endpoint not found"}


class TestMitFrontend:
    @pytest.mark.parametrize("pfad", ["/", "/einstellungen", "/spiele/12/karte", "/index.html"])
    def test_spa_routen_liefern_index(self, client, db, frontend, pfad):
        antwort = client.get(pfad)

        assert antwort.status_code == 200
        assert antwort.text == INDEX
        assert antwort.headers["content-type"].startswith("text/html")

    @pytest.mark.parametrize("pfad", [
        "/api/gibt-es-nicht",
        "/api/matches/1/unbekannt",
        "/api/auth/gibt-es-nicht",
        "/api/",
    ])
    def test_unbekannte_api_liefert_kein_index(self, client, db, frontend, pfad):
        antwort = client.get(pfad)

        assert antwort.status_code == 404
        assert antwort.json() == {"detail": "API endpoint not found"}
        assert "<!doctype" not in antwort.text

    def test_service_worker_ohne_cache(self, client, db, frontend):
        antwort = client.get("/sw.js")

        assert antwort.status_code == 200
        assert "addEventListener" in antwort.text
        assert antwort.headers["cache-control"] == "no-cache"
        assert "javascript" in antwort.headers["content-type"]

    def test_manifest_ohne_cache(self, client, db, frontend):
        antwort = client.get("/manifest.webmanifest")

        assert antwort.status_code == 200
        assert antwort.json() == {"name": "Spesenfuchs"}
        assert antwort.headers["cache-control"] == "no-cache"
        assert antwort.headers["content-type"].startswith("application/manifest+json")

    def test_andere_wurzeldatei_ohne_no_cache(self, client, db, frontend):
        antwort = client.get("/robots.txt")

        assert antwort.status_code == 200
        assert antwort.text == "User-agent: *"
        assert antwort.headers.get("cache-control") != "no-cache"

    def test_appicon(self, client, db, frontend):
        antwort = client.get("/appicon.png")
        assert antwort.status_code == 200
        assert antwort.headers["content-type"] == "image/png"
        assert antwort.content.startswith(b"\x89PNG")

    def test_unterordner_wird_nicht_ausgeliefert(self, client, db, frontend):
        antwort = client.get("/unter/versteckt.txt")
        assert antwort.text == INDEX

    @pytest.mark.parametrize("pfad", ["/..%2Fgeheim.txt", "/%2E%2E/geheim.txt", "/unter/..%2F..%2Fgeheim.txt"])
    def test_kein_ausbruch_aus_dem_frontend(self, client, db, frontend, pfad):
        antwort = client.get(pfad)
        assert "ausserhalb des Frontends" not in antwort.text

    def test_ohne_index_404(self, client, db, frontend):
        (frontend / "index.html").unlink()

        assert client.get("/").json() == {"detail": "Frontend not found"}
        assert client.get("/einstellungen").json() == {"detail": "Frontend not found"}
        # Root files still work
        assert client.get("/sw.js").status_code == 200

    def test_api_routen_gewinnen_gegen_catch_all(self, client, db, frontend):
        assert client.get("/api/health").json()["status"] == "online"


class TestFehlerHandler:
    def test_unerwarteter_fehler_ohne_details(self, client, user, auth_header, monkeypatch):
        def kaputt(user_id):
            raise RuntimeError("sqlite3: /data/app.db ist kaputt, Passwort=hunter2")

        monkeypatch.setattr("api.main_api.get_stammdaten", kaputt)

        antwort = client.get("/api/stammdaten", headers=auth_header)

        assert antwort.status_code == 500
        assert antwort.json() == {"error": {
            "code": "INTERNAL_ERROR",
            "message": "Ein unerwarteter Fehler ist aufgetreten",
            "details": "Der Fehler wurde protokolliert",
        }}
        assert "hunter2" not in antwort.text
        assert "Traceback" not in antwort.text
        assert "RuntimeError" not in antwort.text

    def test_auch_ohne_anmeldung(self, client, db, monkeypatch):
        def kaputt():
            raise ValueError("interner Zustand")

        monkeypatch.setattr("api.main_api.count_distinct_matches", kaputt)

        antwort = client.get("/api/health")

        assert antwort.status_code == 500
        assert fehlerbild(antwort)["code"] == "INTERNAL_ERROR"
        assert "interner Zustand" not in antwort.text

    def test_api_fehler_behalten_ihre_form(self, client, user, auth_header):
        antwort = client.get("/api/saison/99/00", headers=auth_header)
        assert antwort.status_code == 404
        assert set(fehlerbild(antwort)) == {"code", "message"}


class TestCors:
    def test_erlaubter_ursprung(self, client, db):
        antwort = client.options("/api/health", headers={
            "Origin": "https://spesen-generator.jan-vogt.dev",
            "Access-Control-Request-Method": "GET",
        })
        assert antwort.status_code == 200
        assert antwort.headers["access-control-allow-origin"] == "https://spesen-generator.jan-vogt.dev"

    def test_fremder_ursprung(self, client, db):
        antwort = client.get("/api/health", headers={"Origin": "https://boese.example.org"})
        assert "access-control-allow-origin" not in antwort.headers
