"""
Error Handling - Einheitliche Error-Responses
"""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional


class APIError(HTTPException):
    """
    Standardisierte API Error Response.

    Alle Errors haben dieses Format:
    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Benutzerfreundliche Nachricht",
            "details": "Technische Details (optional)"
        }
    }
    """

    def __init__(
            self,
            status_code: int,
            error_code: str,
            message: str,
            details: Optional[str] = None
    ):
        self.error_code = error_code
        self.message = message
        self.details = details

        detail = {
            "error": {
                "code": error_code,
                "message": message
            }
        }

        if details:
            detail["error"]["details"] = details

        super().__init__(status_code=status_code, detail=detail)


# ===== Vordefinierte Error-Typen =====

class AuthenticationError(APIError):
    """401 - Nicht angemeldet oder Token ungültig"""

    def __init__(self, message: str = "Nicht angemeldet", details: Optional[str] = None):
        super().__init__(
            status_code=401,
            error_code="AUTHENTICATION_ERROR",
            message=message,
            details=details
        )


class AuthorizationError(APIError):
    """403 - Keine Berechtigung"""

    def __init__(self, message: str = "Zugriff verweigert", details: Optional[str] = None):
        super().__init__(
            status_code=403,
            error_code="AUTHORIZATION_ERROR",
            message=message,
            details=details
        )


class NotFoundError(APIError):
    """404 - Ressource nicht gefunden"""

    def __init__(self, message: str = "Nicht gefunden", details: Optional[str] = None):
        super().__init__(
            status_code=404,
            error_code="NOT_FOUND",
            message=message,
            details=details
        )


class ValidationError(APIError):
    """400 - Ungültige Eingabe"""

    def __init__(self, message: str = "Ungültige Eingabe", details: Optional[str] = None):
        super().__init__(
            status_code=400,
            error_code="VALIDATION_ERROR",
            message=message,
            details=details
        )


class ConflictError(APIError):
    """409 - Konflikt (z.B. Email bereits vorhanden)"""

    def __init__(self, message: str = "Ressource existiert bereits", details: Optional[str] = None):
        super().__init__(
            status_code=409,
            error_code="CONFLICT",
            message=message,
            details=details
        )


class LoginGesperrtError(APIError):
    """429 - Zu viele falsche Passwoerter hintereinander"""

    def __init__(self, minuten: int):
        einheit = "Minute" if minuten == 1 else "Minuten"
        super().__init__(
            status_code=429,
            error_code="LOGIN_LOCKED",
            message=f"Zu viele Fehlversuche. Der Login ist für {minuten} {einheit} gesperrt.",
        )


class ServerError(APIError):
    """500 - Interner Server-Fehler"""

    def __init__(self, message: str = "Interner Server-Fehler", details: Optional[str] = None):
        super().__init__(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message=message,
            details=details
        )


class CredentialsMissingError(APIError):
    """400 - DFB-Credentials nicht gespeichert"""

    def __init__(self):
        super().__init__(
            status_code=400,
            error_code="CREDENTIALS_MISSING",
            message="Keine DFB-Credentials gespeichert",
            details="Bitte speichere deine DFB-Credentials unter /api/auth/dfb-credentials"
        )

class DFBCredentialsInvalidError(APIError):
    """401 - DFB-Credentials sind ungültig"""

    def __init__(self, details: Optional[str] = None):
        super().__init__(
            status_code=401,
            error_code="DFB_CREDENTIALS_INVALID",
            message="Die DFBnet-Zugangsdaten sind ungültig",
            details=details or "Bitte prüfe Benutzername und Passwort in den Einstellungen"
        )

# ===== Global Exception Handler =====

async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handler für unsere standardisierten APIError Exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Fallback für unerwartete Exceptions.
    Verhindert dass Stacktraces ans Frontend geschickt werden.
    """
    # Log den echten Error (für Debugging)
    import logging
    logger = logging.getLogger("api")
    logger.error(f"Unerwarteter Fehler: {exc}", exc_info=True)

    # Gib generischen Error zurück (keine technischen Details!)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Ein unerwarteter Fehler ist aufgetreten",
                "details": "Der Fehler wurde protokolliert"
            }
        }
    )