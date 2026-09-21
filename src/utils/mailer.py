"""
Versand der Fehlerberichte per SMTP.

Bewusst nur dieser eine Zweck: die Anwendung verschickt sonst keine Post, und
ein allgemeiner Mailversand braechte Vorlagen, Warteschlange und Zustellungs-
protokoll mit, ohne dass irgendetwas davon gebraucht wuerde.

Konfiguriert wird ueber data/.env (siehe .env.example). Fehlt die
Konfiguration, ist der Reiter *Fehler melden* nicht benutzbar und sagt das
auch - stilles Verschlucken waere hier das Schlimmste: der Nutzer haelt seinen
Bericht fuer abgeschickt und niemand hat ihn je gesehen.
"""
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

from core.config import APP_VERSION
from core.errors import APIError
from utils.logger import setup_logger

logger = setup_logger("mailer")

# An diese Adresse gehen die Fehlerberichte, wenn nichts anderes konfiguriert
# ist. Sie darf ueberschrieben werden - wer die Anwendung selbst betreibt,
# moechte seine Berichte in der Regel selbst bekommen.
STANDARD_EMPFAENGER = "spesen-generator@jan-vogt.dev"

TIMEOUT_SEKUNDEN = 20


class MailNichtKonfiguriert(APIError):
    """503 - Es ist kein Postausgang hinterlegt."""

    def __init__(self):
        super().__init__(
            status_code=503,
            error_code="MAIL_NOT_CONFIGURED",
            message="Der Versand von Fehlerberichten ist auf diesem Server nicht eingerichtet.",
            details="In data/.env fehlen SMTP_HOST, SMTP_USER oder SMTP_PASSWORD.",
        )


class MailVersandFehlgeschlagen(APIError):
    """502 - Der Postausgang hat den Bericht nicht angenommen."""

    def __init__(self, details: Optional[str] = None):
        super().__init__(
            status_code=502,
            error_code="MAIL_SEND_FAILED",
            message="Der Fehlerbericht konnte nicht versendet werden. Bitte später erneut versuchen.",
            details=details,
        )


def empfaenger() -> str:
    """Die Adresse, an die Fehlerberichte gehen."""
    return os.getenv("BUGREPORT_EMPFAENGER") or STANDARD_EMPFAENGER


def ist_konfiguriert() -> bool:
    """Ob ein Postausgang hinterlegt ist."""
    return all(os.getenv(name) for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def _port() -> int:
    try:
        return int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        return 587


def sende_bug_report(titel: str, beschreibung: str, bereich: str,
                     schritte: str, absender: str) -> None:
    """
    Schickt einen Fehlerbericht an die hinterlegte Adresse.

    Der Absender ist die Adresse des angemeldeten Nutzers, steht aber nur im
    Reply-To und im Text - als From muss die Adresse des Postausgangs stehen,
    sonst weist ein Empfaenger mit SPF- oder DMARC-Pruefung die Nachricht ab.
    Eine Antwort geht trotzdem an den Melder.

    Raises:
        MailNichtKonfiguriert: wenn kein Postausgang hinterlegt ist.
        MailVersandFehlgeschlagen: wenn der Server die Nachricht ablehnt.
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
        # Port 465 spricht von der ersten Verbindung an TLS, 587 schaltet mit
        # STARTTLS um. Beide Wege sind verbreitet, deshalb beide.
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
        # Der Fehlertext kann Zugangsdaten enthalten, deshalb nur der Typ
        logger.error(f"Fehlerbericht nicht versendet: {type(fehler).__name__}: {fehler}")
        raise MailVersandFehlgeschlagen(type(fehler).__name__) from fehler

    logger.info(f"Fehlerbericht von {absender} an {empfaenger()} versendet")
