"""Ob DFBnet die gespeicherten Zugangsdaten ablehnt - und wie lange schon."""
from datetime import datetime, timedelta, UTC

import pytest

from core.encryption import encrypt_credential
from core.errors import DFBCredentialsInvalidError
from db.database import (
    dfb_login_abgelehnt,
    dfb_login_angenommen,
    get_user_by_id,
    update_dfb_credentials,
)
from db.scrape_runs import get_run, start_run


@pytest.fixture
def mit_zugang(user):
    update_dfb_credentials(user["id"], encrypt_credential("schiri"), encrypt_credential("pw"))
    return user


def _seit(user_id):
    return get_user_by_id(user_id)["dfb_login_abgelehnt_seit"]


class TestMerken:
    def test_anfangs_nichts_abgelehnt(self, mit_zugang):
        assert _seit(mit_zugang["id"]) is None

    def test_ablehnung_wird_gemerkt(self, mit_zugang):
        dfb_login_abgelehnt(mit_zugang["id"])
        seit = datetime.fromisoformat(_seit(mit_zugang["id"]))
        assert datetime.now(UTC) - seit < timedelta(seconds=5)

    def test_erster_zeitpunkt_bleibt(self, mit_zugang, db):
        from db.database import get_connection

        conn = get_connection()
        conn.execute("UPDATE users SET dfb_login_abgelehnt_seit = '2026-10-01T03:00:00+00:00' WHERE id = ?",
                     (mit_zugang["id"],))
        conn.commit()
        conn.close()

        dfb_login_abgelehnt(mit_zugang["id"])
        assert _seit(mit_zugang["id"]) == "2026-10-01T03:00:00+00:00"

    def test_annahme_loescht_hinweis(self, mit_zugang):
        dfb_login_abgelehnt(mit_zugang["id"])
        dfb_login_angenommen(mit_zugang["id"])
        assert _seit(mit_zugang["id"]) is None

    def test_neue_zugangsdaten_loeschen_hinweis(self, mit_zugang):
        dfb_login_abgelehnt(mit_zugang["id"])
        update_dfb_credentials(mit_zugang["id"], encrypt_credential("neu"), encrypt_credential("neu"))
        assert _seit(mit_zugang["id"]) is None

    def test_nur_der_eigene_nutzer(self, mit_zugang):
        from core.security import hash_password
        from db.database import create_user

        anderer = create_user("anderer@example.org", hash_password("x"))
        dfb_login_abgelehnt(mit_zugang["id"])
        assert _seit(anderer) is None


class TestApi:
    def test_me_ohne_ablehnung(self, client, mit_zugang, auth_header):
        daten = client.get("/api/auth/me", headers=auth_header).json()
        assert daten["has_dfb_credentials"] is True
        assert daten["dfb_login_abgelehnt_seit"] is None

    def test_me_meldet_ablehnung(self, client, mit_zugang, auth_header):
        dfb_login_abgelehnt(mit_zugang["id"])
        daten = client.get("/api/auth/me", headers=auth_header).json()
        assert daten["dfb_login_abgelehnt_seit"] == _seit(mit_zugang["id"])

    def test_status_meldet_ablehnung(self, client, mit_zugang, auth_header):
        dfb_login_abgelehnt(mit_zugang["id"])
        daten = client.get("/api/auth/dfb-credentials/status", headers=auth_header).json()
        assert daten["has_credentials"] is True
        assert daten["abgelehnt_seit"] is not None

    def test_ohne_zugangsdaten_kein_hinweis(self, client, user, auth_header):
        daten = client.get("/api/auth/me", headers=auth_header).json()
        assert daten["has_dfb_credentials"] is False
        assert daten["dfb_login_abgelehnt_seit"] is None

    def test_speichern_raeumt_hinweis_ab(self, client, mit_zugang, auth_header):
        dfb_login_abgelehnt(mit_zugang["id"])
        antwort = client.post("/api/auth/dfb-credentials", headers=auth_header,
                              json={"dfb_username": "schiri", "dfb_password": "neues-pw"})
        assert antwort.status_code == 200
        assert client.get("/api/auth/me", headers=auth_header).json()["dfb_login_abgelehnt_seit"] is None


class TestAbrufe:
    """Beide Abrufwege - von Hand und nachts - setzen den Hinweis."""

    @pytest.fixture(params=["api", "scheduler"])
    def abruf(self, request, monkeypatch):
        def abgelehnt(**kwargs):
            raise DFBCredentialsInvalidError("DFBnet meldet: falsches Passwort")

        if request.param == "api":
            import api.main_api as modul

            monkeypatch.setattr(modul, "scrape_matches", abgelehnt)
            return lambda user_id, run_id: modul.run_scrape_process("u", "p", user_id, run_id)

        import scheduler.auto_scrape_scheduler as modul

        monkeypatch.setattr(modul, "scrape_matches", abgelehnt)
        return lambda user_id, run_id: modul.run_scrape_for_user(user_id, "e", "u", "p", run_id)

    def test_ablehnung_setzt_hinweis_und_lauf(self, mit_zugang, abruf):
        run_id = start_run(mit_zugang["id"])
        abruf(mit_zugang["id"], run_id)

        lauf = get_run(run_id)
        assert lauf["status"] == "failed"
        assert lauf["error_code"] == "DFB_CREDENTIALS_INVALID"
        assert _seit(mit_zugang["id"]) is not None

    def test_anderer_fehler_setzt_keinen_hinweis(self, mit_zugang, abruf, monkeypatch):
        import api.main_api
        import scheduler.auto_scrape_scheduler

        def kaputt(**kwargs):
            raise RuntimeError("Playwright abgestuerzt")

        monkeypatch.setattr(api.main_api, "scrape_matches", kaputt)
        monkeypatch.setattr(scheduler.auto_scrape_scheduler, "scrape_matches", kaputt)

        run_id = start_run(mit_zugang["id"])
        abruf(mit_zugang["id"], run_id)

        assert get_run(run_id)["error_code"] == "GENERATION_ERROR"
        assert _seit(mit_zugang["id"]) is None


class TestScrapeMatches:
    """scrape_matches raeumt den Hinweis ab, sobald DFBnet den Login annimmt."""

    class _FakeScraper:
        login_ok = True

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self):
            if not self.login_ok:
                raise DFBCredentialsInvalidError()

        def scrape_all_matches(self, progress_callback=None):
            raise RuntimeError("Abbruch nach dem Login")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def test_angenommener_login_loescht_hinweis(self, mit_zugang, monkeypatch):
        import main

        monkeypatch.setattr(main, "DFBScraper", self._FakeScraper)
        dfb_login_abgelehnt(mit_zugang["id"])

        with pytest.raises(RuntimeError):
            main.scrape_matches("u", "p", user_id=mit_zugang["id"])

        assert _seit(mit_zugang["id"]) is None

    def test_abgelehnter_login_laesst_hinweis(self, mit_zugang, monkeypatch):
        import main

        scraper = type("Abgelehnt", (self._FakeScraper,), {"login_ok": False})
        monkeypatch.setattr(main, "DFBScraper", scraper)
        dfb_login_abgelehnt(mit_zugang["id"])

        with pytest.raises(DFBCredentialsInvalidError):
            main.scrape_matches("u", "p", user_id=mit_zugang["id"])

        assert _seit(mit_zugang["id"]) is not None
