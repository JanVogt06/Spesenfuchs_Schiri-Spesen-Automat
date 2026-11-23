"""
Registrierung, Login, /me, Token-Pruefung und das Hinterlegen der
DFBnet-Zugangsdaten.

Login-Sperre, Ablehnungshinweis und Passwortwechsel haben eigene Dateien
(test_login_sperre.py, test_dfb_login_status.py, test_auth_passwort.py).
"""
from datetime import datetime, timedelta, UTC

import jwt
import pytest

from api_hilfen import (  # noqa: F401 - Fixtures
    datenverzeichnis,
    fehlerbild,
    fremder,
    header_fuer,
    nutzer,
    zugang_hinterlegen,
)


def _registrieren(client, email="neu@example.org", passwort="ein-passwort"):
    return client.post("/api/auth/register", json={"email": email, "password": passwort})


# ===== Registrierung =====

class TestRegistrierung:
    def test_legt_nutzer_an_und_liefert_token(self, client, db):
        from db.database import get_user_by_email

        antwort = _registrieren(client)

        assert antwort.status_code == 201
        daten = antwort.json()
        assert daten["email"] == "neu@example.org"
        assert daten["token_type"] == "bearer"
        assert daten["user_id"] == get_user_by_email("neu@example.org")["id"]

        # Das Token taugt sofort fuer geschuetzte Endpunkte
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {daten['access_token']}"})
        assert me.status_code == 200
        assert me.json()["user_id"] == daten["user_id"]

    def test_passwort_wird_nicht_im_klartext_gespeichert(self, client, db):
        from db.database import get_user_by_email

        _registrieren(client, passwort="klartext-passwort")
        gespeichert = get_user_by_email("neu@example.org")["password_hash"]
        assert "klartext-passwort" not in gespeichert
        assert "$" in gespeichert

    def test_doppelte_adresse_409(self, client, user):
        antwort = _registrieren(client, email=user["email"])

        assert antwort.status_code == 409
        assert fehlerbild(antwort)["code"] == "CONFLICT"

    def test_doppelte_adresse_in_anderer_schreibweise_409(self, client, user):
        antwort = _registrieren(client, email=user["email"].upper())
        assert antwort.status_code == 409

    @pytest.mark.parametrize("passwort", ["", "kurz", "1234567"])
    def test_zu_kurzes_passwort_abgelehnt(self, client, db, passwort):
        from db.database import get_user_by_email

        antwort = _registrieren(client, passwort=passwort)

        assert antwort.status_code in (400, 422)
        assert get_user_by_email("neu@example.org") is None

    def test_passwort_mit_acht_zeichen_reicht(self, client, db):
        assert _registrieren(client, passwort="12345678").status_code == 201

    @pytest.mark.parametrize("email", ["keine-adresse", "a@", "@example.org", ""])
    def test_ungueltige_adresse_422(self, client, db, email):
        assert _registrieren(client, email=email).status_code == 422

    def test_fehlendes_passwort_422(self, client, db):
        assert client.post("/api/auth/register", json={"email": "a@example.org"}).status_code == 422

    def test_ohne_body_422(self, client, db):
        assert client.post("/api/auth/register").status_code == 422


# ===== Login =====

class TestLogin:
    def test_erfolg_liefert_gueltiges_token(self, client, user):
        antwort = client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})

        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["user_id"] == user["id"]
        assert daten["email"] == user["email"]
        assert daten["token_type"] == "bearer"

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {daten['access_token']}"})
        assert me.json()["email"] == user["email"]

    def test_erfolg_wird_protokolliert(self, client, user):
        from db.database import get_connection

        client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})

        conn = get_connection()
        try:
            zeilen = conn.execute("SELECT user_id FROM login_log").fetchall()
        finally:
            conn.close()
        assert [z["user_id"] for z in zeilen] == [user["id"]]

    def test_fehler_im_login_log_verhindert_login_nicht(self, client, user, monkeypatch):
        def kaputt(user_id):
            raise RuntimeError("Platte voll")

        monkeypatch.setattr("api.auth.log_login", kaputt)
        antwort = client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})
        assert antwort.status_code == 200

    def test_falsches_passwort_401(self, client, user):
        antwort = client.post("/api/auth/login", json={"email": user["email"], "password": "falsch"})
        assert antwort.status_code == 401
        assert fehlerbild(antwort)["code"] == "AUTHENTICATION_ERROR"

    def test_ungueltige_adresse_422(self, client, db):
        assert client.post("/api/auth/login", json={"email": "x", "password": "y"}).status_code == 422


# ===== Token-Pruefung =====

def _token(payload: dict, secret: str = None) -> str:
    from core import security

    return jwt.encode(payload, secret or security.SECRET_KEY, algorithm=security.ALGORITHM)


class TestToken:
    def test_me_liefert_eigene_daten(self, client, user, auth_header):
        antwort = client.get("/api/auth/me", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.json() == {
            "user_id": user["id"],
            "email": user["email"],
            "has_dfb_credentials": False,
            "dfb_login_abgelehnt_seit": None,
        }

    def test_me_mit_zugangsdaten(self, client, user, auth_header):
        zugang_hinterlegen(user["id"])
        assert client.get("/api/auth/me", headers=auth_header).json()["has_dfb_credentials"] is True

    def test_me_gibt_keinen_passwort_hash_heraus(self, client, user, auth_header):
        text = client.get("/api/auth/me", headers=auth_header).text
        assert "password" not in text
        assert "dfb_username_encrypted" not in text

    def test_ohne_header_401(self, client, user):
        antwort = client.get("/api/auth/me")
        assert antwort.status_code == 401
        assert fehlerbild(antwort) == {"code": "AUTHENTICATION_ERROR", "message": "Token fehlt"}

    @pytest.mark.parametrize("wert", [
        "Bearer",                 # Token fehlt
        "Bearer a b",             # zu viele Teile
        "Basic abc",              # falsches Schema
        "Token abc",
        "abc",
        "",
    ])
    def test_kaputter_header_401(self, client, user, wert):
        antwort = client.get("/api/auth/me", headers={"Authorization": wert})
        assert antwort.status_code == 401
        assert fehlerbild(antwort)["code"] == "AUTHENTICATION_ERROR"

    def test_schema_ohne_beachtung_der_schreibweise(self, client, user, auth_header):
        token = auth_header["Authorization"].split()[1]
        assert client.get("/api/auth/me", headers={"Authorization": f"bearer {token}"}).status_code == 200

    def test_kein_jwt_401(self, client, user):
        antwort = client.get("/api/auth/me", headers={"Authorization": "Bearer kein.jwt.token"})
        assert antwort.status_code == 401
        assert fehlerbild(antwort)["message"] == "Token ungültig oder abgelaufen"

    def test_abgelaufenes_token_401(self, client, user):
        token = _token({"user_id": user["id"], "exp": datetime.now(UTC) - timedelta(seconds=5)})
        antwort = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert antwort.status_code == 401
        assert fehlerbild(antwort)["message"] == "Token ungültig oder abgelaufen"

    def test_fremd_signiertes_token_401(self, client, user):
        token = _token({"user_id": user["id"], "exp": datetime.now(UTC) + timedelta(days=1)},
                       secret="ein-ganz-anderes-geheimnis-mit-genug-laenge")
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_manipulierte_nutzlast_401(self, client, user, auth_header):
        """Signatur bleibt, die Nutzlast zeigt auf einen anderen Nutzer."""
        import base64
        import json

        anderer = nutzer("opfer@example.org")
        kopf, _, signatur = auth_header["Authorization"].split()[1].split(".")
        nutzlast = base64.urlsafe_b64encode(json.dumps(
            {"user_id": anderer["id"], "exp": int((datetime.now(UTC) + timedelta(days=1)).timestamp())}
        ).encode()).rstrip(b"=").decode()

        antwort = client.get("/api/auth/me", headers={"Authorization": f"Bearer {kopf}.{nutzlast}.{signatur}"})
        assert antwort.status_code == 401

    def test_manipulierte_signatur_401(self, client, user, auth_header):
        token = auth_header["Authorization"].split()[1]
        kaputt = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {kaputt}"}).status_code == 401

    def test_alg_none_401(self, client, user):
        token = jwt.encode({"user_id": user["id"]}, key=None, algorithm="none")
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_token_ohne_user_id_401(self, client, user):
        token = _token({"exp": datetime.now(UTC) + timedelta(days=1)})
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_unbekannter_nutzer_401(self, client, db):
        antwort = client.get("/api/auth/me", headers=header_fuer(4711))
        assert antwort.status_code == 401
        assert fehlerbild(antwort)["message"] == "User nicht gefunden"

    def test_geloeschter_nutzer_401(self, client, user, auth_header):
        from db.database import get_connection

        assert client.get("/api/auth/me", headers=auth_header).status_code == 200

        conn = get_connection()
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        conn.commit()
        conn.close()

        assert client.get("/api/auth/me", headers=auth_header).status_code == 401

    @pytest.mark.parametrize("methode, pfad", [
        ("get", "/api/auth/dfb-credentials/status"),
        ("post", "/api/auth/dfb-credentials"),
        ("post", "/api/generate"),
        ("get", "/api/scrape/status"),
        ("get", "/api/matches"),
        ("post", "/api/matches/expenses"),
        ("get", "/api/matches/1/geo"),
        ("get", "/api/matches/1/download/docx"),
        ("post", "/api/matches/download"),
        ("post", "/api/scheduler/trigger"),
        ("get", "/api/scheduler/status"),
        ("get", "/api/stammdaten"),
        ("get", "/api/saison"),
        ("get", "/api/saison/26/27"),
        ("get", "/api/spielberichte/1"),
        ("get", "/api/spielberichte/1/dokumente/1"),
        ("get", "/api/beobachtungen"),
        ("get", "/api/ligen"),
        ("get", "/api/bugreport/status"),
        ("post", "/api/bugreport"),
    ])
    def test_geschuetzte_endpunkte_ohne_token_401(self, client, db, methode, pfad):
        # Das Token wird vor dem Body geprueft: auch ein unvollstaendiger
        # Body ergibt 401 und keinen 422, der etwas ueber das Schema verraet.
        kwargs = {"json": {}} if methode == "post" else {}
        antwort = getattr(client, methode)(pfad, **kwargs)
        assert antwort.status_code == 401
        assert fehlerbild(antwort)["code"] == "AUTHENTICATION_ERROR"


# ===== DFBnet-Zugangsdaten =====

def _speichern(client, header, benutzer="dfb-schiri", passwort="dfb-pw"):
    return client.post("/api/auth/dfb-credentials", headers=header,
                       json={"dfb_username": benutzer, "dfb_password": passwort})


@pytest.fixture
def mit_bestand(user, datenverzeichnis):
    """
    Ein Nutzer mit hinterlegtem DFBnet-Zugang und Daten in allen vier
    Reitern, die an diesem Zugang haengen - geschrieben ueber die echten
    DB-Funktionen.
    """
    from db.beobachtungen import replace_beobachtungs_saison
    from db.season import replace_saison
    from db.spielberichte import speichere_bericht
    from db.stammdaten import upsert_stammdaten

    zugang_hinterlegen(user["id"], "dfb-schiri", "altes-pw")

    upsert_stammdaten(user["id"], {"name_vorname": "Pfeife, Erika", "plz_ort": "99999 Irgendwo",
                                   "schiedsrichter_seit": "01.07.2010"})
    replace_saison(user["id"], "26/27",
                   spiele=[{"datum": "2026-09-05", "uhrzeit": "15:00", "liga": "Kreisoberliga",
                            "heim": "FC Heim", "gast": "SV Gast", "ergebnis": "2:1",
                            "gespann": [{"rolle": "SR", "name": "Erika Pfeife", "selbst": True}]}],
                   einsaetze=[{"rolle": "SR", "geleitet": "1"}],
                   lehrgaenge={"lehrabend": "3"})
    replace_beobachtungs_saison(user["id"], "schiri-portal", "26/27", [
        {"datum": "2026-09-05", "rolle": "SR", "note": "8.4", "heim": "FC Heim", "gast": "SV Gast"},
    ])
    speichere_bericht(
        user["id"], "26/27",
        {"dfb_spiel_id": "SPIEL1", "datum": "2026-09-05", "uhrzeit": "15:00",
         "heim": "FC Heim", "gast": "SV Gast", "ergebnis": "2:1"},
        {"dokumente": [{"dfb_id": "DOK1", "dateiname": "Sonderbericht.pdf", "kategorie_id": 1}],
         "kategorien": {"1": "Sonderbericht"}},
        {"DOK1": b"%PDF-1.4 inhalt"},
    )
    return user


def _bestand(user_id: int, datenverzeichnis) -> dict:
    from db.beobachtungen import get_beobachtungen
    from db.season import get_saisons
    from db.spielberichte import get_index
    from db.stammdaten import get_stammdaten

    return {
        "stammdaten": get_stammdaten(user_id) is not None,
        "saisons": len(get_saisons(user_id)),
        "beobachtungen": len(get_beobachtungen(user_id)["beobachtungen"]),
        "spielberichte": len(get_index(user_id)),
        "dateien": len(list((datenverzeichnis / "spielberichte").rglob("*.pdf")))
        if (datenverzeichnis / "spielberichte").exists() else 0,
    }


class TestDfbZugangsdaten:
    def test_speichert_verschluesselt(self, client, user, auth_header):
        from core.encryption import decrypt_credential
        from db.database import get_dfb_credentials

        antwort = _speichern(client, auth_header, "mein-login", "mein-pw")

        assert antwort.status_code == 200
        assert antwort.json() == {"success": True, "message": "DFB-Credentials erfolgreich gespeichert"}

        gespeichert = get_dfb_credentials(user["id"])
        assert gespeichert["dfb_username_encrypted"] != "mein-login"
        assert gespeichert["dfb_password_encrypted"] != "mein-pw"
        assert decrypt_credential(gespeichert["dfb_username_encrypted"]) == "mein-login"
        assert decrypt_credential(gespeichert["dfb_password_encrypted"]) == "mein-pw"

    def test_status_vorher_und_nachher(self, client, user, auth_header):
        vorher = client.get("/api/auth/dfb-credentials/status", headers=auth_header).json()
        assert vorher == {"has_credentials": False, "abgelehnt_seit": None,
                          "message": "Keine DFB-Credentials gespeichert"}

        _speichern(client, auth_header)

        nachher = client.get("/api/auth/dfb-credentials/status", headers=auth_header).json()
        assert nachher["has_credentials"] is True
        assert nachher["message"] == "DFB-Credentials gespeichert"

    @pytest.mark.parametrize("benutzer, passwort", [("", "pw"), ("login", ""), ("", "")])
    def test_leere_felder_400(self, client, user, auth_header, benutzer, passwort):
        from db.database import get_dfb_credentials

        antwort = _speichern(client, auth_header, benutzer, passwort)

        assert antwort.status_code == 400
        assert fehlerbild(antwort)["code"] == "VALIDATION_ERROR"
        assert get_dfb_credentials(user["id"]) is None

    def test_fehlendes_feld_422(self, client, user, auth_header):
        antwort = client.post("/api/auth/dfb-credentials", headers=auth_header, json={"dfb_username": "x"})
        assert antwort.status_code == 422

    def test_nur_eigener_nutzer(self, client, user, auth_header, fremder):
        from db.database import get_dfb_credentials

        _speichern(client, auth_header)
        assert get_dfb_credentials(fremder["id"]) is None

    def test_gleiches_konto_behaelt_alle_daten(self, client, mit_bestand, auth_header, datenverzeichnis):
        vorher = _bestand(mit_bestand["id"], datenverzeichnis)
        assert vorher == {"stammdaten": True, "saisons": 1, "beobachtungen": 1,
                          "spielberichte": 1, "dateien": 1}

        # DFBnet erzwingt regelmaessig ein neues Passwort - der Benutzername bleibt
        assert _speichern(client, auth_header, "dfb-schiri", "neues-pw").status_code == 200

        assert _bestand(mit_bestand["id"], datenverzeichnis) == vorher

    def test_anderes_konto_loescht_alle_daten(self, client, mit_bestand, auth_header, datenverzeichnis):
        assert _speichern(client, auth_header, "jemand-anderes", "pw").status_code == 200

        assert _bestand(mit_bestand["id"], datenverzeichnis) == {
            "stammdaten": False, "saisons": 0, "beobachtungen": 0, "spielberichte": 0, "dateien": 0,
        }
        # Und die Endpunkte zeigen die Leerzustaende
        assert client.get("/api/stammdaten", headers=auth_header).json() is None
        assert client.get("/api/saison", headers=auth_header).json() == []

    def test_anderes_konto_laesst_fremde_daten_stehen(self, client, mit_bestand, auth_header,
                                                      datenverzeichnis):
        from db.stammdaten import get_stammdaten, upsert_stammdaten

        anderer = nutzer("kollege@example.org")
        upsert_stammdaten(anderer["id"], {"name_vorname": "Kollege, Karl"})

        _speichern(client, auth_header, "jemand-anderes", "pw")

        assert get_stammdaten(anderer["id"])["name_vorname"] == "Kollege, Karl"

    def test_unlesbarer_alter_zugang_loescht_im_zweifel(self, client, mit_bestand, auth_header,
                                                        datenverzeichnis):
        from db.database import get_connection

        conn = get_connection()
        conn.execute("UPDATE users SET dfb_username_encrypted = 'kein-fernet-token' WHERE id = ?",
                     (mit_bestand["id"],))
        conn.commit()
        conn.close()

        assert _speichern(client, auth_header, "dfb-schiri", "pw").status_code == 200
        assert _bestand(mit_bestand["id"], datenverzeichnis)["stammdaten"] is False
