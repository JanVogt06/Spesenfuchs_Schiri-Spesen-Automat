"""
Error handling - uniform error responses
"""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional


class APIError(HTTPException):
    """
    Standardized API error response.

    All errors have this format:
    {
        "error": {
            "code": "ERROR_CODE",
            "message": "User-friendly message",
            "details": "Technical details (optional)"
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


# ===== Predefined error types =====

class AuthenticationError(APIError):
    """401 - Not logged in or token invalid"""

    def __init__(self, message: str = "Nicht angemeldet", details: Optional[str] = None):
        super().__init__(
            status_code=401,
            error_code="AUTHENTICATION_ERROR",
            message=message,
            details=details
        )


class AuthorizationError(APIError):
    """403 - No permission"""

    def __init__(self, message: str = "Zugriff verweigert", details: Optional[str] = None):
        super().__init__(
            status_code=403,
            error_code="AUTHORIZATION_ERROR",
            message=message,
            details=details
        )


class NotFoundError(APIError):
    """404 - Resource not found"""

    def __init__(self, message: str = "Nicht gefunden", details: Optional[str] = None):
        super().__init__(
            status_code=404,
            error_code="NOT_FOUND",
            message=message,
            details=details
        )


class ValidationError(APIError):
    """400 - Invalid input"""

    def __init__(self, message: str = "Ungültige Eingabe", details: Optional[str] = None):
        super().__init__(
            status_code=400,
            error_code="VALIDATION_ERROR",
            message=message,
            details=details
        )


class ConflictError(APIError):
    """409 - Conflict (e.g. email already exists)"""

    def __init__(self, message: str = "Ressource existiert bereits", details: Optional[str] = None):
        super().__init__(
            status_code=409,
            error_code="CONFLICT",
            message=message,
            details=details
        )


class LoginGesperrtError(APIError):
    """429 - Too many wrong passwords in a row"""

    def __init__(self, minuten: int):
        einheit = "Minute" if minuten == 1 else "Minuten"
        super().__init__(
            status_code=429,
            error_code="LOGIN_LOCKED",
            message=f"Zu viele Fehlversuche. Der Login ist für {minuten} {einheit} gesperrt.",
        )


class ServerError(APIError):
    """500 - Internal server error"""

    def __init__(self, message: str = "Interner Server-Fehler", details: Optional[str] = None):
        super().__init__(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message=message,
            details=details
        )


class CredentialsMissingError(APIError):
    """400 - DFB credentials not stored"""

    def __init__(self):
        super().__init__(
            status_code=400,
            error_code="CREDENTIALS_MISSING",
            message="Keine DFB-Credentials gespeichert",
            details="Bitte speichere deine DFB-Credentials unter /api/auth/dfb-credentials"
        )

class DFBCredentialsInvalidError(APIError):
    """401 - DFB credentials are invalid"""

    def __init__(self, details: Optional[str] = None):
        super().__init__(
            status_code=401,
            error_code="DFB_CREDENTIALS_INVALID",
            message="Die DFBnet-Zugangsdaten sind ungültig",
            details=details or "Bitte prüfe Benutzername und Passwort in den Einstellungen"
        )

# ===== Global exception handlers =====

async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handler for our standardized APIError exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Fallback for unexpected exceptions.
    Prevents stack traces from being sent to the frontend.
    """
    # Log the real error (for debugging)
    import logging
    logger = logging.getLogger("api")
    logger.error(f"Unerwarteter Fehler: {exc}", exc_info=True)

    # Return a generic error (no technical details!)
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