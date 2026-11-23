"""
Abruf starten (/api/generate), Fortschritt pollen (/api/scrape/status),
naechtlicher Scheduler, Health und oeffentliche Statistik.

Es startet nie ein echter Prozess und nie ein Browser: multiprocessing wird
im API-Modul durch eine Attrappe ersetzt.
"""
import types
from datetime import datetime, timedelta, UTC

import pytest

from db_helpers import spiel
from api_hilfen import fehlerbild, nutzer, spiele_anlegen, zugang_hinterlegen


class _Prozess:
    """Zeichnet auf, womit ein Prozess gestartet worden waere."""

    erzeugt = []

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.gestartet = False
        _Prozess.erzeugt.append(self)

    def start(self):
        self.gestartet = True


@pytest.fixture
def prozesse(monkeypatch):
    import api.main_api as modul

    _Prozess.erzeugt = []
    monkeypatch.setattr(modul, "multiprocessing", types.SimpleNamespace(Process=_Prozess))
    return _Prozess.erzeugt


def _veralten(run_id: int, minuten: int = 31) -> None:
    """Setzt das letzte Lebenszeichen eines Laufs in die Vergangenheit."""
    from db.database import get_connection

    alt = (datetime.now(UTC) - timedelta(minutes=minuten)).isoformat()
    conn = get_connection()
    conn.execute("UPDATE scrape_runs SET updated_at = ?, started_at = ? WHERE id = ?", (alt, alt, run_id))
    conn.commit()
    conn.close()


# ===== /api/generate =====

class TestGenerate:
    def test_ohne_zugangsdaten(self, client, user, auth_header, prozesse):
        from db.scrape_runs import get_latest_run

        antwort = client.post("/api/generate", headers=auth_header, json={})

        assert antwort.status_code == 400
        fehler = fehlerbild(antwort)
        assert fehler["code"] == "CREDENTIALS_MISSING"
        assert "details" in fehler
        assert prozesse == []
        assert get_latest_run(user["id"]) is None

    def test_startet_lauf(self, client, user, auth_header, prozesse):
        import api.main_api as modul
        from db.scrape_runs import get_run

        zugang_hinterlegen(user["id"], "dfb-login", "dfb-geheim")

        antwort = client.post("/api/generate", headers=auth_header, json={})

        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["status"] == "pending"
        assert daten["progress"] == {"current": 0, "total": 0, "step": "Starte..."}

        lauf = get_run(daten["run_id"])
        assert lauf["user_id"] == user["id"]
        assert lauf["status"] == "pending"

        assert len(prozesse) == 1
        prozess = prozesse[0]
        assert prozess.gestartet
        assert prozess.daemon is True
        assert prozess.target is modul.run_scrape_process
        # Entschluesselte Zugangsdaten gehen als Parameter mit, nicht ueber ENV
        assert prozess.args == ("dfb-login", "dfb-geheim", user["id"], daten["run_id"])

    def test_body_ist_optional_leer(self, client, user, auth_header, prozesse):
        zugang_hinterlegen(user["id"])
        assert client.post("/api/generate", headers=auth_header, json={"egal": 1}).status_code == 200

    def test_laufender_abruf_409(self, client, user, auth_header, prozesse):
        from db.scrape_runs import get_runs

        zugang_hinterlegen(user["id"])
        assert client.post("/api/generate", headers=auth_header, json={}).status_code == 200

        antwort = client.post("/api/generate", headers=auth_header, json={})

        assert antwort.status_code == 409
        assert fehlerbild(antwort)["code"] == "RUN_ALREADY_ACTIVE"
        assert len(prozesse) == 1
        assert len(get_runs(user["id"])) == 1

    @pytest.mark.parametrize("status", ["pending", "scraping", "generating"])
    def test_jeder_aktive_status_blockiert(self, client, user, auth_header, prozesse, status):
        from db.scrape_runs import start_run, update_run

        zugang_hinterlegen(user["id"])
        update_run(start_run(user["id"]), status=status)

        assert client.post("/api/generate", headers=auth_header, json={}).status_code == 409

    @pytest.mark.parametrize("status", ["completed", "failed"])
    def test_beendeter_lauf_blockiert_nicht(self, client, user, auth_header, prozesse, status):
        from db.scrape_runs import start_run, update_run

        zugang_hinterlegen(user["id"])
        update_run(start_run(user["id"]), status=status, finished=True)

        assert client.post("/api/generate", headers=auth_header, json={}).status_code == 200

    def test_verwaister_lauf_wird_abgeraeumt(self, client, user, auth_header, prozesse):
        from db.scrape_runs import get_run, start_run

        zugang_hinterlegen(user["id"])
        alt = start_run(user["id"])
        _veralten(alt)

        antwort = client.post("/api/generate", headers=auth_header, json={})

        assert antwort.status_code == 200
        assert get_run(alt)["status"] == "failed"
        assert get_run(alt)["error_code"] == "RUN_ABANDONED"

    def test_lauf_eines_anderen_nutzers_blockiert_nicht(self, client, user, auth_header, prozesse):
        from db.scrape_runs import start_run

        anderer = nutzer("anderer@example.org")
        start_run(anderer["id"])
        zugang_hinterlegen(user["id"])

        assert client.post("/api/generate", headers=auth_header, json={}).status_code == 200


# ===== run_scrape_process (ohne Prozess, direkt aufgerufen) =====

class TestScrapeProzess:
    def test_erfolg_schreibt_abschluss(self, user, monkeypatch):
        import api.main_api as modul
        from db.scrape_runs import get_run, start_run

        aufrufe = []

        def scrape(**kwargs):
            aufrufe.append(kwargs)
            kwargs["progress_callback"](1, 2, "Spiel 1 von 2")
            return [{}, {}]

        monkeypatch.setattr(modul, "scrape_matches", scrape)
        run_id = start_run(user["id"])

        modul.run_scrape_process("login", "pw", user["id"], run_id)

        lauf = get_run(run_id)
        assert lauf["status"] == "completed"
        assert lauf["matches_found"] == 2
        assert lauf["step"] == "Fertig!"
        assert lauf["finished_at"] is not None
        assert aufrufe[0]["username"] == "login"
        assert aufrufe[0]["password"] == "pw"
        assert aufrufe[0]["user_id"] == user["id"]

    def test_keine_spiele(self, user, monkeypatch):
        import api.main_api as modul
        from db.scrape_runs import get_run, start_run

        monkeypatch.setattr(modul, "scrape_matches", lambda **kwargs: [])
        run_id = start_run(user["id"])

        modul.run_scrape_process("login", "pw", user["id"], run_id)

        assert get_run(run_id)["step"] == "Keine Spiele gefunden"
        assert get_run(run_id)["status"] == "completed"


# ===== /api/scrape/status =====

class TestScrapeStatus:
    def test_idle_ohne_lauf(self, client, user, auth_header):
        antwort = client.get("/api/scrape/status", headers=auth_header)
        assert antwort.status_code == 200
        assert antwort.json() == {"status": "idle", "progress": None}

    def test_laufender_abruf(self, client, user, auth_header):
        from db.scrape_runs import start_run, update_run

        run_id = start_run(user["id"])
        update_run(run_id, status="scraping", step="Spiel 3 von 7", current=3, total=7)

        daten = client.get("/api/scrape/status", headers=auth_header).json()

        assert daten["run_id"] == run_id
        assert daten["status"] == "scraping"
        assert daten["finished_at"] is None
        assert daten["started_at"]
        assert daten["matches_found"] is None
        assert daten["progress"] == {"current": 3, "total": 7, "step": "Spiel 3 von 7",
                                     "error_code": None, "error_message": None}

    def test_abgeschlossen(self, client, user, auth_header):
        from db.scrape_runs import start_run, update_run

        run_id = start_run(user["id"])
        update_run(run_id, status="completed", step="Fertig!", current=4, total=4,
                   matches_found=4, finished=True)

        daten = client.get("/api/scrape/status", headers=auth_header).json()

        assert daten["status"] == "completed"
        assert daten["matches_found"] == 4
        assert daten["finished_at"] is not None

    def test_fehlgeschlagen_mit_fehlercode(self, client, user, auth_header):
        from db.scrape_runs import start_run, update_run

        run_id = start_run(user["id"])
        update_run(run_id, status="failed", step="Fehler", error_code="DFB_CREDENTIALS_INVALID",
                   error_message="Die DFBnet-Zugangsdaten sind ungültig.", finished=True)

        daten = client.get("/api/scrape/status", headers=auth_header).json()

        assert daten["status"] == "failed"
        assert daten["progress"]["error_code"] == "DFB_CREDENTIALS_INVALID"
        assert daten["progress"]["error_message"] == "Die DFBnet-Zugangsdaten sind ungültig."

    def test_juengster_lauf_zaehlt(self, client, user, auth_header):
        from db.scrape_runs import start_run, update_run

        erster = start_run(user["id"])
        update_run(erster, status="failed", error_code="GENERATION_ERROR", finished=True)
        zweiter = start_run(user["id"])

        daten = client.get("/api/scrape/status", headers=auth_header).json()
        assert daten["run_id"] == zweiter
        assert daten["status"] == "pending"

    def test_verwaister_lauf_wird_als_abgebrochen_gemeldet(self, client, user, auth_header):
        from db.scrape_runs import start_run

        run_id = start_run(user["id"])
        _veralten(run_id)

        daten = client.get("/api/scrape/status", headers=auth_header).json()

        assert daten["status"] == "failed"
        assert daten["progress"]["error_code"] == "RUN_ABANDONED"

    def test_sieht_nur_eigene_laeufe(self, client, user, auth_header):
        from db.scrape_runs import start_run

        anderer = nutzer("anderer@example.org")
        start_run(anderer["id"])

        assert client.get("/api/scrape/status", headers=auth_header).json()["status"] == "idle"


# ===== Scheduler =====

class _Scheduler:
    def __init__(self):
        self.aufrufe = 0

    def scrape_all_users(self):
        self.aufrufe += 1

        async def nichts():
            return None

        return nichts()

    def get_status(self):
        return {"running": True, "is_processing": False, "next_run": "2026-11-24 03:00:00+01:00"}


@pytest.fixture
def scheduler(monkeypatch):
    import api.main_api as modul

    attrappe = _Scheduler()
    monkeypatch.setattr(modul, "get_scheduler", lambda: attrappe)
    return attrappe


class TestScheduler:
    def test_trigger_standardmaessig_gesperrt(self, client, user, auth_header, scheduler, monkeypatch):
        monkeypatch.delenv("ALLOW_SCHEDULER_TRIGGER", raising=False)

        antwort = client.post("/api/scheduler/trigger", headers=auth_header)

        assert antwort.status_code == 403
        assert fehlerbild(antwort)["code"] == "TRIGGER_DISABLED"
        assert scheduler.aufrufe == 0

    @pytest.mark.parametrize("wert", ["0", "false", "no", "", "ja"])
    def test_trigger_bleibt_gesperrt(self, client, user, auth_header, scheduler, monkeypatch, wert):
        monkeypatch.setenv("ALLOW_SCHEDULER_TRIGGER", wert)

        assert client.post("/api/scheduler/trigger", headers=auth_header).status_code == 403
        assert scheduler.aufrufe == 0

    @pytest.mark.parametrize("wert", ["1", "true", "TRUE", "yes"])
    def test_trigger_freigegeben(self, client, user, auth_header, scheduler, monkeypatch, wert):
        monkeypatch.setenv("ALLOW_SCHEDULER_TRIGGER", wert)

        antwort = client.post("/api/scheduler/trigger", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.json()["success"] is True
        assert scheduler.aufrufe == 1

    def test_trigger_ohne_token_auch_wenn_freigegeben(self, client, db, scheduler, monkeypatch):
        monkeypatch.setenv("ALLOW_SCHEDULER_TRIGGER", "1")
        assert client.post("/api/scheduler/trigger").status_code == 401
        assert scheduler.aufrufe == 0

    def test_status(self, client, user, auth_header, scheduler):
        antwort = client.get("/api/scheduler/status", headers=auth_header)
        assert antwort.status_code == 200
        assert antwort.json() == scheduler.get_status()

    def test_status_des_echten_nicht_gestarteten_schedulers(self, client, user, auth_header):
        # Ohne Lifespan laeuft der Scheduler nicht - der Endpunkt sagt das
        daten = client.get("/api/scheduler/status", headers=auth_header).json()
        assert daten["running"] is False
        assert daten["is_processing"] is False
        assert set(daten) == {"running", "is_processing", "next_run"}


# ===== Health und Statistik =====

class TestHealthUndStatistik:
    def test_health(self, client, db):
        from core import config

        antwort = client.get("/api/health")

        assert antwort.status_code == 200
        assert antwort.json() == {"status": "online", "service": "Spesenfuchs API",
                                  "version": config.APP_VERSION, "matches": 0}

    def test_health_ohne_token(self, client, db):
        assert client.get("/api/health").status_code == 200

    def test_statistik_leer(self, client, db):
        assert client.get("/api/stats/public").json() == {"matches_total": 0}

    def test_statistik_zaehlt_verschiedene_spiele(self, client, user):
        """Dasselbe Spiel bei zwei Unparteiischen zaehlt einmal."""
        kollege = nutzer("kollege@example.org")
        gemeinsam = spiel(heim="FC Gemeinsam", gast="SV Geteilt")

        spiele_anlegen(user["id"], gemeinsam, spiel(heim="FC Allein", gast="SV Solo"))
        spiele_anlegen(kollege["id"], gemeinsam)

        assert client.get("/api/stats/public").json() == {"matches_total": 2}
        assert client.get("/api/health").json()["matches"] == 2

    def test_statistik_faellt_bei_fehler_auf_null(self, client, db, monkeypatch):
        def kaputt():
            raise RuntimeError("Datenbank weg")

        monkeypatch.setattr("api.main_api.count_distinct_matches", kaputt)

        antwort = client.get("/api/stats/public")
        assert antwort.status_code == 200
        assert antwort.json() == {"matches_total": 0}
