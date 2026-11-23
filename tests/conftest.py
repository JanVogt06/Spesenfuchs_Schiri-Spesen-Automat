"""
Gemeinsame Fixtures.

Die Umgebung wird gesetzt, bevor irgendein Modul aus src importiert wird:
core.security liest JWT_SECRET_KEY beim Import, db.database legt den
Datenbankpfad beim Import fest. Nichts davon darf je die echte data/ im
Projekt beruehren - deshalb zeigt alles in ein Wegwerf-Verzeichnis.
"""
import os
import tempfile
from pathlib import Path

_SITZUNG = Path(tempfile.mkdtemp(prefix="spesenfuchs-tests-"))

os.environ["DATA_DIR"] = str(_SITZUNG)
os.environ["DATABASE_PATH"] = str(_SITZUNG / "import.db")
os.environ["ENV_FILE"] = str(_SITZUNG / "nicht-vorhanden.env")
os.environ["LOG_FILE"] = str(_SITZUNG / "logs" / "test.log")
os.environ["OUTPUT_DIR"] = str(_SITZUNG / "output")
os.environ["FRONTEND_DIR"] = str(_SITZUNG / "kein-frontend")
os.environ["JWT_SECRET_KEY"] = "test-secret-nur-fuer-pytest-und-lang-genug"
os.environ["ENCRYPTION_KEY"] = "Zz0n2bS0b5rH7m3Zl5t1Yp6S1QyQ3Qe2b6Lk6c1wP9Q="
for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALLOW_SCHEDULER_TRIGGER"):
    os.environ.pop(name, None)

import pytest  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Eine frische, voll migrierte Datenbank je Test."""
    import db.database as database

    pfad = tmp_path / "app.db"
    monkeypatch.setattr(database, "DB_PATH", pfad)
    database.init_database()
    return pfad


@pytest.fixture
def client(db):
    """
    TestClient ohne Lifespan: der wuerde den naechtlichen Scheduler starten.
    Die Datenbank kommt aus der db-Fixture.
    """
    from fastapi.testclient import TestClient
    from api.main_api import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def user(db):
    """Ein angelegter Nutzer mit bekanntem Passwort."""
    from core.security import hash_password
    from db.database import create_user

    user_id = create_user("schiri@example.org", hash_password("richtig-geheim"))
    return {"id": user_id, "email": "schiri@example.org", "password": "richtig-geheim"}


@pytest.fixture
def auth_header(user):
    """Authorization-Header fuer den Nutzer aus der user-Fixture."""
    from core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user['id'])}"}
