"""
Sending the bug reports - without a real SMTP server.

smtplib.SMTP and smtplib.SMTP_SSL are replaced by a stub that remembers how
it was used and, on request, fails at a specific point.
"""
import smtplib
import socket

import pytest

from core.config import APP_VERSION
from utils import mailer
from utils.mailer import (
    STANDARD_EMPFAENGER,
    TIMEOUT_SEKUNDEN,
    MailNichtKonfiguriert,
    MailVersandFehlgeschlagen,
    _fehlermeldung,
    empfaenger,
    ist_konfiguriert,
    sende_bug_report,
)

SMTP_VARIABLEN = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_PORT", "SMTP_FROM",
                  "BUGREPORT_EMPFAENGER")


class FalscherServer:
    """Stub for smtplib.SMTP / SMTP_SSL."""

    instanzen = []

    def __init__(self, host, port, timeout=None, fehler_bei=None, fehler=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.fehler_bei, self.fehler = fehler_bei, fehler
        self.schritte = []
        self.login_daten = None
        self.nachrichten = []
        if fehler_bei == "connect":
            raise fehler
        FalscherServer.instanzen.append(self)

    def _schritt(self, name):
        self.schritte.append(name)
        if self.fehler_bei == name:
            raise self.fehler

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.schritte.append("quit")
        return False

    def starttls(self):
        self._schritt("starttls")

    def login(self, user, password):
        self.login_daten = (user, password)
        self._schritt("login")

    def send_message(self, nachricht):
        self.nachrichten.append(nachricht)
        self._schritt("send_message")


@pytest.fixture
def smtp_leer(monkeypatch):
    """No SMTP configuration in the environment."""
    for name in SMTP_VARIABLEN:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def smtp_konfiguriert(monkeypatch, smtp_leer):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_USER", "postausgang@example.org")
    monkeypatch.setenv("SMTP_PASSWORD", "geheim")


@pytest.fixture
def server(monkeypatch):
    """Replaces both SMTP classes and provides a control for errors."""
    FalscherServer.instanzen = []
    steuerung = {"klasse": None, "fehler_bei": None, "fehler": None}

    def baue(klasse):
        def fabrik(host, port, timeout=None):
            steuerung["klasse"] = klasse
            return FalscherServer(host, port, timeout, steuerung["fehler_bei"], steuerung["fehler"])
        return fabrik

    monkeypatch.setattr(mailer.smtplib, "SMTP", baue("SMTP"))
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", baue("SMTP_SSL"))
    return steuerung


def _senden(**ueberschreiben):
    argumente = dict(
        titel="Download geht nicht",
        beschreibung="Beim Klick passiert nichts.",
        bereich="Downloads",
        schritte="1. Klicken\n2. Warten",
        absender="melder@example.org",
    )
    argumente.update(ueberschreiben)
    sende_bug_report(**argumente)


def _gesendet():
    assert len(FalscherServer.instanzen) == 1
    instanz = FalscherServer.instanzen[0]
    assert len(instanz.nachrichten) == 1
    return instanz, instanz.nachrichten[0]


# ===== Configuration =====

class TestKonfiguration:
    def test_ohne_alles_nicht_konfiguriert(self, smtp_leer):
        assert ist_konfiguriert() is False

    def test_vollstaendig(self, smtp_konfiguriert):
        assert ist_konfiguriert() is True

    @pytest.mark.parametrize("fehlt", ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"])
    def test_jede_angabe_ist_pflicht(self, smtp_konfiguriert, monkeypatch, fehlt):
        monkeypatch.delenv(fehlt)
        assert ist_konfiguriert() is False

    def test_leerer_wert_zaehlt_als_fehlend(self, smtp_konfiguriert, monkeypatch):
        monkeypatch.setenv("SMTP_PASSWORD", "")
        assert ist_konfiguriert() is False

    def test_standard_empfaenger(self, smtp_leer):
        assert empfaenger() == STANDARD_EMPFAENGER

    def test_eigener_empfaenger(self, smtp_leer, monkeypatch):
        monkeypatch.setenv("BUGREPORT_EMPFAENGER", "betreiber@example.org")
        assert empfaenger() == "betreiber@example.org"

    @pytest.mark.parametrize("wert, port", [
        (None, 587), ("587", 587), ("465", 465), ("25", 25), ("kein-port", 587),
    ])
    def test_port(self, smtp_leer, monkeypatch, wert, port):
        if wert is not None:
            monkeypatch.setenv("SMTP_PORT", wert)
        assert mailer._port() == port

    def test_ohne_konfiguration_kein_versuch(self, smtp_leer, server):
        with pytest.raises(MailNichtKonfiguriert) as info:
            _senden()
        assert info.value.status_code == 503
        assert info.value.error_code == "MAIL_NOT_CONFIGURED"
        assert FalscherServer.instanzen == []


# ===== Sending =====

class TestVersand:
    def test_standardport_mit_starttls(self, smtp_konfiguriert, server):
        _senden()
        instanz, _ = _gesendet()
        assert server["klasse"] == "SMTP"
        assert (instanz.host, instanz.port) == ("smtp.example.org", 587)
        assert instanz.timeout == TIMEOUT_SEKUNDEN
        assert instanz.schritte == ["starttls", "login", "send_message", "quit"]
        assert instanz.login_daten == ("postausgang@example.org", "geheim")

    def test_port_465_mit_ssl_ohne_starttls(self, smtp_konfiguriert, server, monkeypatch):
        monkeypatch.setenv("SMTP_PORT", "465")
        _senden()
        instanz, _ = _gesendet()
        assert server["klasse"] == "SMTP_SSL"
        assert instanz.port == 465
        assert "starttls" not in instanz.schritte
        assert instanz.schritte == ["login", "send_message", "quit"]

    def test_anderer_port_mit_starttls(self, smtp_konfiguriert, server, monkeypatch):
        monkeypatch.setenv("SMTP_PORT", "2525")
        _senden()
        instanz, _ = _gesendet()
        assert server["klasse"] == "SMTP"
        assert instanz.port == 2525
        assert instanz.schritte[0] == "starttls"

    def test_kaputter_port_faellt_auf_587(self, smtp_konfiguriert, server, monkeypatch):
        monkeypatch.setenv("SMTP_PORT", "abc")
        _senden()
        instanz, _ = _gesendet()
        assert instanz.port == 587

    def test_from_ist_postausgang_reply_to_der_melder(self, smtp_konfiguriert, server):
        _senden()
        _, nachricht = _gesendet()
        assert nachricht["From"] == "postausgang@example.org"
        assert nachricht["Reply-To"] == "melder@example.org"
        assert nachricht["To"] == STANDARD_EMPFAENGER

    def test_smtp_from_ueberschreibt_absender(self, smtp_konfiguriert, server, monkeypatch):
        monkeypatch.setenv("SMTP_FROM", "Spesenfuchs <noreply@example.org>")
        _senden()
        _, nachricht = _gesendet()
        assert nachricht["From"] == "Spesenfuchs <noreply@example.org>"
        assert nachricht["Reply-To"] == "melder@example.org"
        # Login still happens with the account
        assert FalscherServer.instanzen[0].login_daten[0] == "postausgang@example.org"

    def test_eigener_empfaenger(self, smtp_konfiguriert, server, monkeypatch):
        monkeypatch.setenv("BUGREPORT_EMPFAENGER", "betreiber@example.org")
        _senden()
        _, nachricht = _gesendet()
        assert nachricht["To"] == "betreiber@example.org"

    def test_betreff_mit_version(self, smtp_konfiguriert, server):
        _senden()
        _, nachricht = _gesendet()
        assert nachricht["Subject"] == f"[Spesenfuchs {APP_VERSION}] Download geht nicht"

    def test_text(self, smtp_konfiguriert, server):
        _senden()
        _, nachricht = _gesendet()
        text = nachricht.get_content()
        assert "Melder:  melder@example.org" in text
        assert "Bereich: Downloads" in text
        assert f"Version: {APP_VERSION}" in text
        assert "Beim Klick passiert nichts." in text
        assert "1. Klicken\n2. Warten" in text

    def test_leere_felder_als_strich(self, smtp_konfiguriert, server):
        _senden(bereich="", schritte="")
        _, nachricht = _gesendet()
        text = nachricht.get_content()
        assert "Bereich: —" in text
        assert "------------------------\n—\n" in text


# ===== Errors =====

class TestFehler:
    @pytest.mark.parametrize("fehler_bei, fehler, fragment", [
        ("login", smtplib.SMTPAuthenticationError(535, b"auth failed"), "Zugangsdaten abgelehnt"),
        ("connect", TimeoutError("timed out"), "Zeitüberschreitung"),
        ("connect", socket.timeout("timed out"), "Zeitüberschreitung"),
        ("connect", ConnectionRefusedError(61, "refused"), "Verbindung abgelehnt"),
        ("connect", socket.gaierror(8, "nodename"), "nicht auflösbar"),
        ("send_message", smtplib.SMTPRecipientsRefused({}), "später erneut"),
        ("starttls", smtplib.SMTPNotSupportedError("no tls"), "später erneut"),
        ("connect", OSError("netz weg"), "später erneut"),
    ])
    def test_wird_zu_versandfehler(self, smtp_konfiguriert, server, fehler_bei, fehler, fragment):
        server["fehler_bei"], server["fehler"] = fehler_bei, fehler
        with pytest.raises(MailVersandFehlgeschlagen) as info:
            _senden()
        assert info.value.status_code == 502
        assert info.value.error_code == "MAIL_SEND_FAILED"
        assert fragment in info.value.message
        # Only the type, never the error text - it may contain credentials
        assert info.value.details == type(fehler).__name__
        assert info.value.__cause__ is fehler

    def test_andere_ausnahmen_werden_nicht_verschluckt(self, smtp_konfiguriert, server):
        server["fehler_bei"], server["fehler"] = "send_message", ValueError("programmierfehler")
        with pytest.raises(ValueError):
            _senden()

    def test_passwort_nicht_in_der_antwort(self, smtp_konfiguriert, server):
        server["fehler_bei"] = "login"
        server["fehler"] = smtplib.SMTPAuthenticationError(535, b"bad password geheim")
        with pytest.raises(MailVersandFehlgeschlagen) as info:
            _senden()
        assert "geheim" not in info.value.message
        assert "geheim" not in (info.value.details or "")

    def test_passwort_nicht_im_protokoll(self, smtp_konfiguriert, server, monkeypatch):
        zeilen = []
        monkeypatch.setattr(mailer.logger, "error", lambda text, *a, **k: zeilen.append(text))
        server["fehler_bei"] = "login"
        server["fehler"] = smtplib.SMTPAuthenticationError(535, b"bad password geheim")
        with pytest.raises(MailVersandFehlgeschlagen):
            _senden()
        assert len(zeilen) == 1
        assert "geheim" not in zeilen[0]
        assert "SMTPAuthenticationError (SMTP 535)" in zeilen[0]


class TestFehlermeldung:
    def test_authentifizierung(self):
        text = _fehlermeldung(smtplib.SMTPAuthenticationError(535, b"x"), "smtp.web.de", 587)
        assert text.startswith("smtp.web.de hat die Zugangsdaten abgelehnt")
        assert "App-Passwort" in text

    def test_zeitueberschreitung_nennt_host_und_port(self):
        text = _fehlermeldung(TimeoutError(), "smtp.web.de", 465)
        assert text.startswith("Keine Verbindung zu smtp.web.de:465")

    def test_abgelehnt_nennt_host_und_port(self):
        text = _fehlermeldung(ConnectionRefusedError(), "smtp.web.de", 25)
        assert text == "smtp.web.de:25 hat die Verbindung abgelehnt. Stimmen Adresse und Port?"

    def test_namensaufloesung(self):
        text = _fehlermeldung(socket.gaierror(), "smpt.web.de", 587)
        assert text.startswith("smpt.web.de ist nicht auflösbar")

    def test_sonstiges(self):
        text = _fehlermeldung(smtplib.SMTPServerDisconnected(), "h", 1)
        assert text == "Der Fehlerbericht konnte nicht versendet werden. Bitte später erneut versuchen."

    def test_ausnahmeklassen_im_api_format(self):
        fehler = MailVersandFehlgeschlagen("kaputt", "SMTPException")
        assert fehler.detail == {
            "error": {"code": "MAIL_SEND_FAILED", "message": "kaputt", "details": "SMTPException"}
        }
        assert MailNichtKonfiguriert().detail["error"]["details"].startswith("In data/.env fehlen")
