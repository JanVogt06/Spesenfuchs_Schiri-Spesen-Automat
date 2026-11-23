"""
Gemeinsame Hilfen fuer die API-Tests (test_api_*.py).

Enthaelt selbst keine Tests. Die anderen API-Testdateien importieren die
Fixtures und Funktionen von hier - tests/ liegt beim Lauf auf sys.path,
genau wie fuer db_helpers.
"""
import pytest

from db_helpers import spiel


def header_fuer(user_id: int) -> dict:
    from core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def nutzer(email: str, passwort: str = "richtig-geheim") -> dict:
    """Legt einen Nutzer ueber die echte DB-Funktion an."""
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
    Schreibt Spiele ueber main.persist_matches - also genau den Weg, den ein
    Scrape nimmt - und liefert ihre IDs in der Reihenfolge der Eingabe.
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
    """Ein NOFV-Pflichtspiel (Regionalliga Nordost) - bekommt die XLSX-Quittung."""
    return spiel(
        heim=kwargs.pop("heim", "FC Carl Zeiss Jena"),
        gast=kwargs.pop("gast", "BSG Chemie Leipzig"),
        spielklasse="Regionalliga Nordost",
        staffel="Regionalliga Nordost",
        mannschaftsart="Herren",
        **kwargs,
    )


def fehlerbild(antwort) -> dict:
    """Der error-Block der einheitlichen Fehlerantwort."""
    daten = antwort.json()
    assert set(daten) == {"error"}, daten
    return daten["error"]


@pytest.fixture
def datenverzeichnis(tmp_path, monkeypatch):
    """
    Eigenes DATA_DIR je Test. Spielbericht-Dokumente landen auf der Platte
    unter DATA_DIR - ohne das teilten sich alle Tests einen Ordner.
    """
    pfad = tmp_path / "data"
    pfad.mkdir()
    monkeypatch.setenv("DATA_DIR", str(pfad))
    return pfad


@pytest.fixture
def fremder(db):
    """Ein zweiter Nutzer, der die Daten des ersten nie sehen darf."""
    return nutzer("fremder@example.org")
