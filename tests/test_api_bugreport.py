"""
Bug reports: status and sending.

No mail ever goes out - either sende_bug_report is replaced, or smtplib in
the mailer module is a stub that only records.
"""
import smtplib
import types

import pytest

from api_hilfen import fehlerbild

SMTP_VARIABLEN = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_PORT", "SMTP_FROM", "BUGREPORT_EMPFAENGER")


@pytest.fixture(autouse=True)
def ohne_postausgang(monkeypatch):
    for name in SMTP_VARIABLEN:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def postausgang(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_USER", "postausgang@example.org")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-geheim")


class _Smtp:
    """An SMTP server that sends nothing but records."""

    verschickt = []
    fehler = None

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, benutzer, passwort):
        if _Smtp.fehler:
            raise _Smtp.fehler

    def send_message(self, nachricht):
        _Smtp.verschickt.append((self.host, self.port, nachricht))


@pytest.fixture
def smtp(monkeypatch):
    import utils.mailer as mailer

    _Smtp.verschickt = []
    _Smtp.fehler = None
    monkeypatch.setattr(mailer, "smtplib", types.SimpleNamespace(
        SMTP=_Smtp,
        SMTP_SSL=_Smtp,
        SMTPException=smtplib.SMTPException,
        SMTPAuthenticationError=smtplib.SMTPAuthenticationError,
    ))
    return _Smtp


@pytest.fixture
def versand(monkeypatch):
    """Replaces sende_bug_report in the API module and remembers the calls."""
    aufrufe = []
    monkeypatch.setattr("api.main_api.sende_bug_report", lambda **kwargs: aufrufe.append(kwargs))
    return aufrufe


def _melden(client, header, **felder):
    body = {"titel": "Karte leer", "beschreibung": "Die Karte zeigt nichts an."}
    body.update(felder)
    return client.post("/api/bugreport", headers=header, json=body)


class TestStatus:
    def test_ohne_postausgang(self, client, user, auth_header):
        from utils.mailer import STANDARD_EMPFAENGER

        antwort = client.get("/api/bugreport/status", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.json() == {"verfuegbar": False, "empfaenger": STANDARD_EMPFAENGER}

    def test_unvollstaendiger_postausgang(self, client, user, auth_header, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
        monkeypatch.setenv("SMTP_USER", "x@example.org")
        assert client.get("/api/bugreport/status", headers=auth_header).json()["verfuegbar"] is False

    def test_mit_postausgang_und_eigenem_empfaenger(self, client, user, auth_header, postausgang, monkeypatch):
        monkeypatch.setenv("BUGREPORT_EMPFAENGER", "betreiber@example.org")

        assert client.get("/api/bugreport/status", headers=auth_header).json() == {
            "verfuegbar": True, "empfaenger": "betreiber@example.org",
        }


class TestSenden:
    def test_ohne_postausgang_klarer_fehler(self, client, user, auth_header, smtp):
        antwort = _melden(client, auth_header)

        # Not silently swallowed: the user learns that nothing arrived
        assert antwort.status_code == 503
        fehler = fehlerbild(antwort)
        assert fehler["code"] == "MAIL_NOT_CONFIGURED"
        assert "SMTP_HOST" in fehler["details"]
        assert smtp.verschickt == []

    def test_erfolg_mit_absender_aus_der_datenbank(self, client, user, auth_header, versand):
        antwort = _melden(client, auth_header, titel="  Karte leer  ", beschreibung="\nNichts zu sehen\n",
                          bereich=" Karte ", schritte=" 1. Spiel oeffnen ",
                          absender="faelschung@example.org", email="faelschung@example.org")

        assert antwort.status_code == 200
        assert antwort.json() == {"status": "gesendet"}
        assert versand == [{
            "titel": "Karte leer",
            "beschreibung": "Nichts zu sehen",
            "bereich": "Karte",
            "schritte": "1. Spiel oeffnen",
            "absender": user["email"],
        }]

    def test_optionale_felder_leer(self, client, user, auth_header, versand):
        assert _melden(client, auth_header).status_code == 200
        assert versand[0]["bereich"] == ""
        assert versand[0]["schritte"] == ""

    @pytest.mark.parametrize("felder", [
        {"titel": "   "},
        {"beschreibung": ""},
        {"titel": "\t", "beschreibung": "\n"},
    ])
    def test_leere_pflichtfelder_400(self, client, user, auth_header, versand, felder):
        antwort = _melden(client, auth_header, **felder)

        assert antwort.status_code == 400
        assert fehlerbild(antwort)["code"] == "VALIDATION_ERROR"
        assert versand == []

    @pytest.mark.parametrize("body", [{}, {"titel": "nur titel"}, {"beschreibung": "nur text"}])
    def test_fehlende_felder_422(self, client, user, auth_header, versand, body):
        assert client.post("/api/bugreport", headers=auth_header, json=body).status_code == 422
        assert versand == []

    def test_nachricht_ueber_den_echten_mailer(self, client, user, auth_header, postausgang, smtp,
                                               monkeypatch):
        from core.config import APP_VERSION

        monkeypatch.setenv("BUGREPORT_EMPFAENGER", "betreiber@example.org")

        antwort = _melden(client, auth_header, bereich="Karte")

        assert antwort.status_code == 200
        ((host, port, nachricht),) = smtp.verschickt
        assert (host, port) == ("smtp.example.org", 587)
        assert nachricht["To"] == "betreiber@example.org"
        assert nachricht["From"] == "postausgang@example.org"
        assert nachricht["Reply-To"] == user["email"]
        assert nachricht["Subject"] == f"[Spesenfuchs {APP_VERSION}] Karte leer"
        text = nachricht.get_content()
        assert "Die Karte zeigt nichts an." in text
        assert user["email"] in text

    def test_server_lehnt_ab_502(self, client, user, auth_header, postausgang, smtp):
        smtp.fehler = smtplib.SMTPAuthenticationError(535, b"Authentication failed smtp-geheim")

        antwort = _melden(client, auth_header)

        assert antwort.status_code == 502
        fehler = fehlerbild(antwort)
        assert fehler["code"] == "MAIL_SEND_FAILED"
        assert "smtp.example.org hat die Zugangsdaten abgelehnt" in fehler["message"]
        assert fehler["details"] == "SMTPAuthenticationError"
        # The server's error text (may contain credentials) does not go out
        assert "smtp-geheim" not in antwort.text
        assert smtp.verschickt == []
