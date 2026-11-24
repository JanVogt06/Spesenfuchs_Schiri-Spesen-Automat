"""
Sending of error reports via SMTP.

Deliberately only this one purpose: the application sends no other mail, and
general mail sending would bring templates, a queue and a delivery
log with it, without any of it being needed.

Configured via data/.env (see .env.example). If the
configuration is missing, the *Fehler melden* (report an error) tab is unusable and says so
- silently swallowing would be the worst here: the user believes their
report was sent and nobody ever saw it.
"""
import os
import smtplib
import socket
from email.message import EmailMessage
from typing import Optional

from core.config import APP_VERSION
from core.errors import APIError
from utils.logger import setup_logger

logger = setup_logger("mailer")

# Error reports go to this address unless configured otherwise.
# It may be overridden - whoever runs the application themselves
# usually wants to receive their reports themselves.
STANDARD_EMPFAENGER = "spesen-generator@jan-vogt.dev"

TIMEOUT_SEKUNDEN = 20


class MailNichtKonfiguriert(APIError):
    """503 - No outbox is configured."""

    def __init__(self):
        super().__init__(
            status_code=503,
            error_code="MAIL_NOT_CONFIGURED",
            message="Der Versand von Fehlerberichten ist auf diesem Server nicht eingerichtet.",
            details="In data/.env fehlen SMTP_HOST, SMTP_USER oder SMTP_PASSWORD.",
        )


class MailVersandFehlgeschlagen(APIError):
    """502 - The outbox did not accept the report."""

    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(
            status_code=502,
            error_code="MAIL_SEND_FAILED",
            message=message,
            details=details,
        )


def _fehlermeldung(fehler: Exception, host: str, port: int) -> str:
    """
    Translates an SMTP error into a sentence that leads to the cause.

    The distinction is half of the troubleshooting: a timeout
    means the server cannot get out at all - usually the
    provider blocks outgoing mail ports. A rejected login, by contrast, means
    the connection is up and only the credentials do not match. Anyone who mixes
    these up searches for hours in the wrong place.
    """
    if isinstance(fehler, smtplib.SMTPAuthenticationError):
        return (f"{host} hat die Zugangsdaten abgelehnt. Bei web.de und GMX muss der Zugriff "
                "durch Mailprogramme erst freigeschaltet werden; mit Zwei-Faktor-Anmeldung "
                "wird ein App-Passwort gebraucht.")

    if isinstance(fehler, (TimeoutError, socket.timeout)):
        return (f"Keine Verbindung zu {host}:{port} - Zeitüberschreitung. Der Server kommt auf "
                "diesem Port nicht hinaus; viele Anbieter sperren ausgehende Mailports, "
                "manche geben sie auf Anfrage frei.")

    if isinstance(fehler, ConnectionRefusedError):
        return f"{host}:{port} hat die Verbindung abgelehnt. Stimmen Adresse und Port?"

    if isinstance(fehler, socket.gaierror):
        return f"{host} ist nicht auflösbar. Stimmt die Schreibweise, und hat der Server einen Namensdienst?"

    return "Der Fehlerbericht konnte nicht versendet werden. Bitte später erneut versuchen."


def empfaenger() -> str:
    """The address to which error reports go."""
    return os.getenv("BUGREPORT_EMPFAENGER") or STANDARD_EMPFAENGER


def ist_konfiguriert() -> bool:
    """Whether an outbox is configured."""
    return all(os.getenv(name) for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def _port() -> int:
    try:
        return int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        return 587


def sende_bug_report(titel: str, beschreibung: str, bereich: str,
                     schritte: str, absender: str) -> None:
    """
    Sends an error report to the stored address.

    The sender is the address of the logged-in user, but appears only in
    Reply-To and in the text - the outbox's address has to be the From,
    otherwise a recipient with SPF or DMARC checks rejects the message.
    A reply still goes to the reporter.

    Raises:
            MailNichtKonfiguriert: if no outbox is configured.
            MailVersandFehlgeschlagen: if the server rejects the message.
    """
    if not ist_konfiguriert():
        raise MailNichtKonfiguriert()

    nachricht = EmailMessage()
    nachricht["Subject"] = f"[Spesenfuchs {APP_VERSION}] {titel}"
    nachricht["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER")
    nachricht["To"] = empfaenger()
    nachricht["Reply-To"] = absender

    nachricht.set_content(
        "\n".join(
            [
                f"Melder:  {absender}",
                f"Bereich: {bereich or '—'}",
                f"Version: {APP_VERSION}",
                "",
                "Beschreibung",
                "------------",
                beschreibung,
                "",
                "Schritte zum Nachstellen",
                "------------------------",
                schritte or "—",
                "",
            ]
        )
    )

    host = os.getenv("SMTP_HOST")
    port = _port()

    try:
        # Port 465 speaks TLS from the first connection, 587 switches over with
        # STARTTLS. Both ways are common, hence both.
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SEKUNDEN) as server:
                server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
                server.send_message(nachricht)
        else:
            with smtplib.SMTP(host, port, timeout=TIMEOUT_SEKUNDEN) as server:
                server.starttls()
                server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
                server.send_message(nachricht)
    except (smtplib.SMTPException, OSError) as fehler:
        # The server's error text may contain credentials - neither into the
        # response nor into the log. Type, SMTP code and our own interpretation
        # suffice for troubleshooting.
        meldung = _fehlermeldung(fehler, host, port)
        code = getattr(fehler, "smtp_code", None)
        logger.error(
            f"Fehlerbericht nicht versendet: {type(fehler).__name__}"
            f"{f' (SMTP {code})' if code else ''} - {meldung}"
        )
        raise MailVersandFehlgeschlagen(meldung, type(fehler).__name__) from fehler

    logger.info(f"Fehlerbericht an {empfaenger()} versendet")
