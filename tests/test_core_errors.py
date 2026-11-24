"""
core.errors: uniform error format and the two global handlers.

The handlers are tested on a small FastAPI app of their own so that the test
does not depend on the routes of the real application; one test additionally
checks that the real app has registered them.
"""
import asyncio
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.errors import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    CredentialsMissingError,
    DFBCredentialsInvalidError,
    LoginGesperrtError,
    NotFoundError,
    ServerError,
    ValidationError,
    api_error_handler,
    generic_exception_handler,
)


# ===== Format =====

class TestFormat:
    def test_mit_details(self):
        fehler = APIError(418, "TEEKANNE", "Ich bin eine Teekanne", "RFC 2324")
        assert fehler.status_code == 418
        assert fehler.detail == {
            "error": {"code": "TEEKANNE", "message": "Ich bin eine Teekanne", "details": "RFC 2324"}
        }
        assert (fehler.error_code, fehler.message, fehler.details) == \
            ("TEEKANNE", "Ich bin eine Teekanne", "RFC 2324")

    def test_ohne_details_kein_schluessel(self):
        fehler = APIError(400, "X", "y")
        assert fehler.detail == {"error": {"code": "X", "message": "y"}}

    def test_leere_details_kein_schluessel(self):
        assert "details" not in APIError(400, "X", "y", "").detail["error"]

    @pytest.mark.parametrize("klasse, status, code, nachricht", [
        (AuthenticationError, 401, "AUTHENTICATION_ERROR", "Nicht angemeldet"),
        (AuthorizationError, 403, "AUTHORIZATION_ERROR", "Zugriff verweigert"),
        (NotFoundError, 404, "NOT_FOUND", "Nicht gefunden"),
        (ValidationError, 400, "VALIDATION_ERROR", "Ungültige Eingabe"),
        (ConflictError, 409, "CONFLICT", "Ressource existiert bereits"),
        (ServerError, 500, "INTERNAL_ERROR", "Interner Server-Fehler"),
    ])
    def test_vordefinierte_fehler(self, klasse, status, code, nachricht):
        fehler = klasse()
        assert isinstance(fehler, APIError)
        assert fehler.status_code == status
        assert fehler.detail == {"error": {"code": code, "message": nachricht}}

    @pytest.mark.parametrize("klasse", [
        AuthenticationError, AuthorizationError, NotFoundError,
        ValidationError, ConflictError, ServerError,
    ])
    def test_eigene_nachricht_und_details(self, klasse):
        fehler = klasse("Eigene Nachricht", "mehr dazu")
        assert fehler.detail["error"]["message"] == "Eigene Nachricht"
        assert fehler.detail["error"]["details"] == "mehr dazu"

    def test_credentials_fehlen(self):
        fehler = CredentialsMissingError()
        assert fehler.status_code == 400
        assert fehler.detail["error"]["code"] == "CREDENTIALS_MISSING"
        assert "/api/auth/dfb-credentials" in fehler.detail["error"]["details"]

    def test_dfb_credentials_ungueltig(self):
        fehler = DFBCredentialsInvalidError()
        assert fehler.status_code == 401
        assert fehler.detail["error"]["code"] == "DFB_CREDENTIALS_INVALID"
        assert fehler.detail["error"]["details"].startswith("Bitte prüfe")
        assert DFBCredentialsInvalidError("Konto gesperrt").detail["error"]["details"] == "Konto gesperrt"

    def test_login_gesperrt_mehrzahl(self):
        fehler = LoginGesperrtError(15)
        assert fehler.status_code == 429
        assert fehler.detail["error"]["code"] == "LOGIN_LOCKED"
        assert fehler.detail["error"]["message"] == \
            "Zu viele Fehlversuche. Der Login ist für 15 Minuten gesperrt."

    def test_login_gesperrt_einzahl(self):
        assert "für 1 Minute gesperrt" in LoginGesperrtError(1).detail["error"]["message"]


# ===== Handler directly =====

class TestHandlerDirekt:
    def test_api_error_handler(self):
        antwort = asyncio.run(api_error_handler(None, NotFoundError("Spiel fehlt", "id 7")))
        assert antwort.status_code == 404
        assert json.loads(antwort.body) == {
            "error": {"code": "NOT_FOUND", "message": "Spiel fehlt", "details": "id 7"}
        }

    def test_generic_handler_verraet_nichts(self, caplog):
        with caplog.at_level(logging.ERROR, logger="api"):
            antwort = asyncio.run(generic_exception_handler(None, RuntimeError("geheimes Detail")))
        assert antwort.status_code == 500
        inhalt = json.loads(antwort.body)
        assert inhalt == {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Ein unerwarteter Fehler ist aufgetreten",
                "details": "Der Fehler wurde protokolliert",
            }
        }
        assert "geheimes Detail" not in antwort.body.decode()
        # ...but it is in the log
        assert any("geheimes Detail" in r.getMessage() for r in caplog.records)


# ===== Handler in an app =====

@pytest.fixture
def app_client():
    app = FastAPI()
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    @app.get("/nicht-gefunden")
    def nicht_gefunden():
        raise NotFoundError("Spiel nicht gefunden")

    @app.get("/gesperrt")
    def gesperrt():
        raise LoginGesperrtError(3)

    @app.get("/kaputt")
    def kaputt():
        raise KeyError("intern")

    return TestClient(app, raise_server_exceptions=False)


class TestHandlerInApp:
    def test_api_error(self, app_client):
        antwort = app_client.get("/nicht-gefunden")
        assert antwort.status_code == 404
        assert antwort.json() == {"error": {"code": "NOT_FOUND", "message": "Spiel nicht gefunden"}}

    def test_unterklasse(self, app_client):
        antwort = app_client.get("/gesperrt")
        assert antwort.status_code == 429
        assert antwort.json()["error"]["code"] == "LOGIN_LOCKED"

    def test_unerwartete_ausnahme(self, app_client):
        antwort = app_client.get("/kaputt")
        assert antwort.status_code == 500
        assert antwort.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "intern" not in antwort.text

    def test_echte_app_registriert_die_handler(self):
        from api.main_api import app

        assert app.exception_handlers[APIError] is api_error_handler
        assert app.exception_handlers[Exception] is generic_exception_handler
