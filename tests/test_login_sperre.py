"""Login-Sperre nach fuenf falschen Passwoertern."""
from datetime import datetime, timedelta, UTC

import pytest

from db import login_sperren
from db.login_sperren import (
    MAX_FEHLVERSUCHE,
    SPERRDAUER_MINUTEN,
    fehlversuch_merken,
    fehlversuche_loeschen,
    gesperrt_bis,
)


def _login(client, email, passwort):
    return client.post("/api/auth/login", json={"email": email, "password": passwort})


class TestZaehler:
    def test_ohne_fehlversuch_nicht_gesperrt(self, db):
        assert gesperrt_bis("a@example.org") is None

    def test_zaehlt_verbleibende_versuche_herunter(self, db):
        reste = [fehlversuch_merken("a@example.org") for _ in range(MAX_FEHLVERSUCHE)]
        assert reste == [4, 3, 2, 1, 0]

    def test_fuenfter_fehlversuch_sperrt(self, db):
        jetzt = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
        for _ in range(MAX_FEHLVERSUCHE):
            fehlversuch_merken("a@example.org", jetzt)
        assert gesperrt_bis("a@example.org", jetzt) == jetzt + timedelta(minutes=SPERRDAUER_MINUTEN)

    def test_sperre_laeuft_ab(self, db):
        jetzt = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
        for _ in range(MAX_FEHLVERSUCHE):
            fehlversuch_merken("a@example.org", jetzt)
        spaeter = jetzt + timedelta(minutes=SPERRDAUER_MINUTEN, seconds=1)
        assert gesperrt_bis("a@example.org", spaeter) is None

    def test_nach_ablauf_wieder_volle_versuche(self, db):
        jetzt = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
        for _ in range(MAX_FEHLVERSUCHE):
            fehlversuch_merken("a@example.org", jetzt)
        spaeter = jetzt + timedelta(minutes=SPERRDAUER_MINUTEN, seconds=1)
        assert fehlversuch_merken("a@example.org", spaeter) == MAX_FEHLVERSUCHE - 1

    def test_alte_fehlversuche_verfallen(self, db):
        jetzt = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
        for _ in range(MAX_FEHLVERSUCHE - 1):
            fehlversuch_merken("a@example.org", jetzt)
        spaeter = jetzt + timedelta(minutes=SPERRDAUER_MINUTEN)
        assert fehlversuch_merken("a@example.org", spaeter) == MAX_FEHLVERSUCHE - 1
        assert gesperrt_bis("a@example.org", spaeter) is None

    def test_schreibweise_der_adresse_egal(self, db):
        fehlversuch_merken("A@Example.org")
        assert fehlversuch_merken("  a@example.ORG ") == MAX_FEHLVERSUCHE - 2

    def test_adressen_getrennt(self, db):
        for _ in range(MAX_FEHLVERSUCHE):
            fehlversuch_merken("a@example.org")
        assert gesperrt_bis("b@example.org") is None

    def test_loeschen_setzt_zurueck(self, db):
        for _ in range(MAX_FEHLVERSUCHE - 1):
            fehlversuch_merken("a@example.org")
        fehlversuche_loeschen("a@example.org")
        assert fehlversuch_merken("a@example.org") == MAX_FEHLVERSUCHE - 1


class TestLoginEndpunkt:
    def test_richtiges_passwort(self, client, user):
        antwort = _login(client, user["email"], user["password"])
        assert antwort.status_code == 200
        assert antwort.json()["user_id"] == user["id"]

    def test_erste_fehlversuche_ohne_hinweis(self, client, user):
        for _ in range(MAX_FEHLVERSUCHE - 3):
            antwort = _login(client, user["email"], "falsch")
            assert antwort.status_code == 401
            assert antwort.json()["error"]["message"] == "Falsche Email oder Passwort"

    def test_warnt_vor_den_letzten_versuchen(self, client, user):
        meldungen = [_login(client, user["email"], "falsch").json()["error"]["message"]
                     for _ in range(MAX_FEHLVERSUCHE - 1)]
        assert "Noch 2 Versuche" in meldungen[-2]
        assert "Noch 1 Versuch," in meldungen[-1]

    def test_fuenfter_fehlversuch_sperrt(self, client, user):
        for _ in range(MAX_FEHLVERSUCHE - 1):
            _login(client, user["email"], "falsch")
        antwort = _login(client, user["email"], "falsch")
        assert antwort.status_code == 429
        assert antwort.json()["error"]["code"] == "LOGIN_LOCKED"
        assert f"{SPERRDAUER_MINUTEN} Minuten" in antwort.json()["error"]["message"]

    def test_gesperrt_auch_mit_richtigem_passwort(self, client, user):
        for _ in range(MAX_FEHLVERSUCHE):
            _login(client, user["email"], "falsch")
        antwort = _login(client, user["email"], user["password"])
        assert antwort.status_code == 429

    def test_erfolg_setzt_zaehler_zurueck(self, client, user):
        for _ in range(MAX_FEHLVERSUCHE - 1):
            _login(client, user["email"], "falsch")
        assert _login(client, user["email"], user["password"]).status_code == 200
        for _ in range(MAX_FEHLVERSUCHE - 1):
            assert _login(client, user["email"], "falsch").status_code == 401

    def test_unbekannte_adresse_wird_genauso_gesperrt(self, client, db):
        for _ in range(MAX_FEHLVERSUCHE - 1):
            antwort = _login(client, "gibtsnicht@example.org", "x")
            assert antwort.status_code == 401
        assert _login(client, "gibtsnicht@example.org", "x").status_code == 429

    def test_restminuten_aufgerundet(self, client, user, monkeypatch):
        bis = datetime.now(UTC) + timedelta(seconds=61)
        monkeypatch.setattr("api.auth.gesperrt_bis", lambda email: bis)
        meldung = _login(client, user["email"], user["password"]).json()["error"]["message"]
        assert "2 Minuten" in meldung

    def test_eine_minute_im_singular(self, client, user, monkeypatch):
        bis = datetime.now(UTC) + timedelta(seconds=5)
        monkeypatch.setattr("api.auth.gesperrt_bis", lambda email: bis)
        meldung = _login(client, user["email"], user["password"]).json()["error"]["message"]
        assert "1 Minute " in meldung
