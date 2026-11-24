"""Scrape runs: progress, most recent run, double-start lock and orphaned runs."""
import pytest

import db.database as database
from db import scrape_runs
from db.scrape_runs import (
    ACTIVE_STATUS,
    STALE_AFTER_MINUTES,
    fail_stale_runs,
    get_latest_run,
    get_run,
    get_runs,
    has_active_run,
    start_run,
    update_run,
)
from db_helpers import feste_uhr, nutzer_anlegen


@pytest.fixture
def uhr(monkeypatch):
    return feste_uhr(monkeypatch, scrape_runs)


@pytest.fixture
def zweiter(db):
    conn = database.get_connection()
    try:
        return nutzer_anlegen(conn, "kollege@example.org")
    finally:
        conn.close()


class TestStartUndUpdate:
    def test_start(self, user, uhr):
        run = get_run(start_run(user["id"]))
        assert run["user_id"] == user["id"]
        assert run["status"] == "pending"
        assert run["step"] == "Initialisierung..."
        assert (run["current_item"], run["total_items"]) == (0, 0)
        assert run["started_at"] == run["updated_at"] == "2026-11-23T12:00:00+00:00"
        assert run["finished_at"] is None

    def test_nur_uebergebene_felder(self, user, uhr):
        rid = start_run(user["id"])
        update_run(rid, status="scraping", current=3, total=10)
        uhr.weiter(minutes=1)
        update_run(rid, step="Spiel 4")
        run = get_run(rid)
        assert (run["status"], run["step"], run["current_item"], run["total_items"]) == \
            ("scraping", "Spiel 4", 3, 10)
        assert run["updated_at"] == "2026-11-23T12:01:00+00:00"
        assert run["finished_at"] is None

    def test_null_ist_ein_wert(self, user, uhr):
        rid = start_run(user["id"])
        update_run(rid, current=5, matches_found=5)
        update_run(rid, current=0, matches_found=0)
        run = get_run(rid)
        assert (run["current_item"], run["matches_found"]) == (0, 0)

    def test_abschluss_setzt_finished_at(self, user, uhr):
        rid = start_run(user["id"])
        uhr.weiter(minutes=3)
        update_run(rid, status="failed", error_code="DFB_CREDENTIALS_INVALID",
                   error_message="Login fehlgeschlagen", finished=True)
        run = get_run(rid)
        assert run["finished_at"] == "2026-11-23T12:03:00+00:00"
        assert run["error_code"] == "DFB_CREDENTIALS_INVALID"

    def test_unbekannter_lauf(self, db):
        assert get_run(999) is None
        update_run(999, status="completed")  # must not fail


class TestLatest:
    def test_juengster_lauf_des_nutzers(self, user, zweiter, uhr):
        start_run(user["id"])
        uhr.weiter(minutes=5)
        neu = start_run(user["id"])
        uhr.weiter(minutes=5)
        start_run(zweiter)
        assert get_latest_run(user["id"])["id"] == neu

    def test_gleiche_startzeit_hoehere_id(self, user, uhr):
        start_run(user["id"])
        zweiter_lauf = start_run(user["id"])
        assert get_latest_run(user["id"])["id"] == zweiter_lauf

    def test_ohne_lauf(self, user):
        assert get_latest_run(user["id"]) is None

    def test_runs_neueste_zuerst_mit_limit(self, user, uhr):
        ids = []
        for _ in range(4):
            ids.append(start_run(user["id"]))
            uhr.weiter(minutes=1)
        assert [r["id"] for r in get_runs(user["id"], limit=3)] == ids[::-1][:3]
        assert len(get_runs(user["id"])) == 4


class TestAktiv:
    @pytest.mark.parametrize("status", ACTIVE_STATUS)
    def test_aktive_status(self, user, uhr, status):
        rid = start_run(user["id"])
        update_run(rid, status=status)
        assert has_active_run(user["id"]) is True

    @pytest.mark.parametrize("status", ["completed", "failed"])
    def test_abgeschlossen(self, user, uhr, status):
        rid = start_run(user["id"])
        update_run(rid, status=status, finished=True)
        assert has_active_run(user["id"]) is False

    def test_nutzer_getrennt(self, user, zweiter, uhr):
        start_run(user["id"])
        assert has_active_run(zweiter) is False


class TestVerwaisteLaeufe:
    def test_alter_lauf_wird_abgebrochen(self, user, uhr):
        rid = start_run(user["id"])
        update_run(rid, status="scraping")
        uhr.weiter(minutes=STALE_AFTER_MINUTES + 1)

        assert fail_stale_runs() == 1
        run = get_run(rid)
        assert run["status"] == "failed"
        assert run["error_code"] == "RUN_ABANDONED"
        assert run["step"] == "Abgebrochen"
        assert run["finished_at"] == run["updated_at"] == "2026-11-23T12:31:00+00:00"
        assert has_active_run(user["id"]) is False

    def test_lebenszeichen_haelt_lauf_am_leben(self, user, uhr):
        rid = start_run(user["id"])
        uhr.weiter(minutes=STALE_AFTER_MINUTES - 1)
        update_run(rid, step="noch da")
        uhr.weiter(minutes=STALE_AFTER_MINUTES - 1)
        assert fail_stale_runs() == 0
        assert get_run(rid)["status"] == "pending"

    def test_knapp_unter_der_grenze(self, user, uhr):
        start_run(user["id"])
        uhr.weiter(minutes=STALE_AFTER_MINUTES - 1, seconds=59)
        assert fail_stale_runs() == 0

    def test_abgeschlossene_bleiben(self, user, uhr):
        rid = start_run(user["id"])
        update_run(rid, status="completed", finished=True)
        uhr.weiter(days=1)
        assert fail_stale_runs() == 0
        assert get_run(rid)["status"] == "completed"
        assert get_run(rid)["error_code"] is None

    def test_alle_nutzer(self, user, zweiter, uhr):
        start_run(user["id"])
        start_run(zweiter)
        uhr.weiter(hours=2)
        assert fail_stale_runs() == 2
