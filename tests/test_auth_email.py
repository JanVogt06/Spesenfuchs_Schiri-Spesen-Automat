"""E-Mail-Adressen ohne Ruecksicht auf Gross-/Kleinschreibung."""
from core.security import hash_password
from db.database import create_user, get_user_by_email


def test_login_in_anderer_schreibweise(client, user):
    antwort = client.post("/api/auth/login", json={"email": "  Schiri@Example.ORG", "password": user["password"]})
    assert antwort.status_code == 200
    assert antwort.json()["user_id"] == user["id"]


def test_registrierung_speichert_klein(client, db):
    antwort = client.post("/api/auth/register", json={"email": "Neu@Example.org", "password": "12345678"})
    assert antwort.status_code == 201
    assert antwort.json()["email"] == "neu@example.org"
    assert get_user_by_email("NEU@example.org")["email"] == "neu@example.org"


def test_altbestand_mit_zwei_schreibweisen_bevorzugt_exakte(db):
    """Vor dem Fix konnten zwei Konten derselben Adresse entstehen."""
    alt = create_user("Doppelt@example.org", hash_password("a"))
    neu = create_user("doppelt@example.org", hash_password("b"))
    assert get_user_by_email("doppelt@example.org")["id"] == neu
    assert get_user_by_email("Doppelt@example.org")["id"] == alt
    assert get_user_by_email("DOPPELT@example.org")["id"] == alt  # sonst die aelteste
