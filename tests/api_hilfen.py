"""
Shared helpers for the API tests (test_api_*.py).

Contains no tests itself. The other API test files import the fixtures and
functions from here - tests/ is on sys.path during a run, just like for
db_helpers.
"""
import pytest

from db_helpers import spiel


def header_fuer(user_id: int) -> dict:
    from core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def nutzer(email: str, passwort: str = "richtig-geheim") -> dict:
    """Creates a user through the real DB function."""
    from core.security import hash_password
    from db.database import create_user

    user_id = create_user(email, hash_password(passwort))
    return {"id": user_id, "email": email, "password": passwort, "header": header_fuer(user_id)}


def zugang_hinterlegen(user_id: int, benutzer: str = "dfb-schiri", passwort: str = "dfb-pw") -> None:
    from core.encryption import encrypt_credential
    from db.database import update_dfb_credentials

    update_dfb_credentials(user_id, encrypt_credential(benutzer), encrypt_credential(passwort))


def spiele_anlegen(user_id: int, *spiele: dict) -> list:
    """
    Writes matches via main.persist_matches - exactly the path a scrape takes -
    and returns their IDs in input order.
    """
    from db.matches import build_match_key, get_matches_for_user
    from main import persist_matches
    from utils.match_utils import extract_iso_date_from_anpfiff

    assert persist_matches(user_id, list(spiele)) == len(spiele)

    nach_key = {m["match_key"]: m["id"] for m in get_matches_for_user(user_id)}
    ids = []
    for s in spiele:
        datum = extract_iso_date_from_anpfiff(s["spiel_info"]["anpfiff"])
        ids.append(nach_key[build_match_key(s["spiel_info"], s["spielstaette"], datum)])
    return ids


def nofv_spiel(**kwargs) -> dict:
    """A NOFV compulsory match (Regionalliga Nordost) - gets the XLSX receipt."""
    return spiel(
        heim=kwargs.pop("heim", "FC Carl Zeiss Jena"),
        gast=kwargs.pop("gast", "BSG Chemie Leipzig"),
        spielklasse="Regionalliga Nordost",
        staffel="Regionalliga Nordost",
        mannschaftsart="Herren",
        **kwargs,
    )


def fehlerbild(antwort) -> dict:
    """The error block of the uniform error response."""
    daten = antwort.json()
    assert set(daten) == {"error"}, daten
    return daten["error"]


@pytest.fixture
def datenverzeichnis(tmp_path, monkeypatch):
    """
    Own DATA_DIR per test. Match report documents end up on disk under DATA_DIR -
    without this, all tests would share one folder.
    """
    pfad = tmp_path / "data"
    pfad.mkdir()
    monkeypatch.setenv("DATA_DIR", str(pfad))
    return pfad


@pytest.fixture
def fremder(db):
    """A second user who must never see the first one's data."""
    return nutzer("fremder@example.org")
