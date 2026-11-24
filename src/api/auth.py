"""
Authentication endpoints - register and login with JWT + DFB credentials
"""
import math
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, EmailStr
from typing import Optional

from db.database import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    update_dfb_credentials,
    get_dfb_credentials,
    update_user_password,
    log_login
)
from db.login_sperren import (
    MAX_FEHLVERSUCHE,
    SPERRDAUER_MINUTEN,
    gesperrt_bis,
    fehlversuch_merken,
    fehlversuche_loeschen,
)
from db.stammdaten import delete_stammdaten
from db.season import delete_saisons
from db.beobachtungen import delete_beobachtungen
from db.spielberichte import delete_spielberichte
from core.security import hash_password, verify_password, create_access_token, decode_access_token
from core.encryption import encrypt_credential, decrypt_credential
from core.errors import (
    AuthenticationError,
    ConflictError,
    LoginGesperrtError,
    ValidationError
)
from utils.logger import setup_logger

logger = setup_logger("auth")

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Applies equally to registration and password change. The frontend
# checks the same thing, but anyone calling the API directly would
# otherwise bypass it.
MIN_PASSWORT_LAENGE = 8


# ===== Request/Response Models =====

class RegisterRequest(BaseModel):
    """Register request"""
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Auth response with token"""
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str


class UserInfo(BaseModel):
    """User information"""
    user_id: int
    email: str
    has_dfb_credentials: bool
    # Since when DFBnet has been rejecting the stored credentials (ISO, UTC)
    dfb_login_abgelehnt_seit: Optional[str] = None


class DFBCredentialsRequest(BaseModel):
    """DFB credentials request"""
    dfb_username: str
    dfb_password: str


class DFBCredentialsResponse(BaseModel):
    """DFB credentials response"""
    success: bool
    message: str

class ChangePasswordRequest(BaseModel):
    """Change-password request"""
    current_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    """Change-password response"""
    success: bool
    message: str


# ===== Dependency: Get Current User =====

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Extracts the user from the JWT token.

    
    Used as a dependency: current_user = Depends(get_current_user)
    """
    if not authorization:
        raise AuthenticationError("Token fehlt")

    # Extract the token from "Bearer TOKEN"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise AuthenticationError("Ungültiges Token-Format")
    except ValueError:
        raise AuthenticationError("Ungültiges Token-Format")

    # Decode the token
    user_id = decode_access_token(token)
    if not user_id:
        raise AuthenticationError("Token ungültig oder abgelaufen")

    # Load the user from the DB
    user = get_user_by_id(user_id)
    if not user:
        raise AuthenticationError("User nicht gefunden")

    return user


# ===== Endpoints =====

@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(request: RegisterRequest):
    """
    Registers a new user and returns a token.

    - Checks whether the email already exists
    - Hashes the password securely
    - Creates the user in the DB
    - Returns a JWT token
    """
    if len(request.password) < MIN_PASSWORT_LAENGE:
        raise ValidationError(f"Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen lang sein")

    # Stored in lower case; get_user_by_email compares case-insensitively
    # anyway.
    email = request.email.strip().lower()

    if get_user_by_email(email):
        raise ConflictError("Email bereits registriert")

    password_hash = hash_password(request.password)
    user_id = create_user(email, password_hash)
    token = create_access_token(user_id)

    return AuthResponse(
        access_token=token,
        user_id=user_id,
        email=email
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Login with email and password, returns a token.

    After MAX_FEHLVERSUCHE wrong passwords in a row the address is locked
    for SPERRDAUER_MINUTEN - also for the correct password, otherwise
    guessing could continue during the lock.
    """
    if bis := gesperrt_bis(request.email):
        minuten = math.ceil((bis - datetime.now(UTC)).total_seconds() / 60)
        raise LoginGesperrtError(max(minuten, 1))

    user = get_user_by_email(request.email)

    # An unknown address and a wrong password count the same, so that
    # neither the message nor the lock reveals whether an account exists.
    if not user or not verify_password(request.password, user['password_hash']):
        verbleibend = fehlversuch_merken(request.email)

        if verbleibend == 0:
            logger.warning(f"Login nach {MAX_FEHLVERSUCHE} Fehlversuchen gesperrt")
            raise LoginGesperrtError(SPERRDAUER_MINUTEN)

        if verbleibend <= 2:
            versuche = "Versuch" if verbleibend == 1 else "Versuche"
            raise AuthenticationError(
                f"Falsche Email oder Passwort. Noch {verbleibend} {versuche}, "
                f"danach ist der Login {SPERRDAUER_MINUTEN} Minuten gesperrt."
            )

        raise AuthenticationError("Falsche Email oder Passwort")

    fehlversuche_loeschen(request.email)

    # Create token
    token = create_access_token(user['id'])

    # Record the login (best effort, must never block the login)
    try:
        log_login(user['id'])
    except Exception:
        pass

    return AuthResponse(
        access_token=token,
        user_id=user['id'],
        email=user['email']
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Returns information about the currently logged-in user.
    Requires a token in the Authorization header.
    """
    # Check whether the user has stored DFB credentials
    dfb_creds = get_dfb_credentials(current_user['id'])

    return UserInfo(
        user_id=current_user['id'],
        email=current_user['email'],
        has_dfb_credentials=dfb_creds is not None,
        dfb_login_abgelehnt_seit=current_user.get('dfb_login_abgelehnt_seit') if dfb_creds else None,
    )


@router.post("/dfb-credentials", response_model=DFBCredentialsResponse)
async def save_dfb_credentials(
    request: DFBCredentialsRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Stores the DFB credentials encrypted for the user.

    These credentials are used automatically when generating,
    so the user does not have to enter them every time.
    """
    user_id = current_user['id']

    # Validation
    if not request.dfb_username or not request.dfb_password:
        raise ValidationError("DFB Username und Passwort müssen angegeben werden")

    # Encrypt
    encrypted_username = encrypt_credential(request.dfb_username)
    encrypted_password = encrypt_credential(request.dfb_password)

    # Does the new login still belong to the same DFBnet account? Must be
    # checked BEFORE overwriting.
    try:
        bisher = get_dfb_credentials(user_id)
        gleiches_konto = bool(bisher) and decrypt_credential(
            bisher['dfb_username_encrypted']
        ) == request.dfb_username
    except Exception:
        # If the old username can no longer be decrypted, delete when in doubt:
        # better an empty tab than someone else's personal data.
        gleiches_konto = False

    # Save to DB
    update_dfb_credentials(user_id, encrypted_username, encrypted_password)

    # The stored master data belongs to the previous DFBnet account. If
    # someone points the app at another account, the name, address and date
    # of birth of another person would show there until the next successful
    # fetch - so remove them.
    #
    # A pure password change, by contrast, leaves them in place. DFBnet
    # enforces one regularly; if it took the master data with it, the tab
    # would be empty every time until the next nightly run.
    if not gleiches_konto:
        delete_stammdaten(user_id)
        delete_saisons(user_id)
        delete_beobachtungen(user_id)
        delete_spielberichte(user_id)

    return DFBCredentialsResponse(
        success=True,
        message="DFB-Credentials erfolgreich gespeichert"
    )


@router.get("/dfb-credentials/status")
async def check_dfb_credentials(current_user: dict = Depends(get_current_user)):
    """
    Checks whether the user has stored DFB credentials.
    """
    user_id = current_user['id']
    dfb_creds = get_dfb_credentials(user_id)

    return {
        "has_credentials": dfb_creds is not None,
        "abgelehnt_seit": current_user.get('dfb_login_abgelehnt_seit') if dfb_creds else None,
        "message": "DFB-Credentials gespeichert" if dfb_creds else "Keine DFB-Credentials gespeichert"
    }

@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
        request: ChangePasswordRequest,
        current_user: dict = Depends(get_current_user)
):
    """
    Changes the password of the logged-in user.

    - Checks whether the current password is correct
    - Validates the new password (minimum length)
    - Hashes and stores the new password
    """
    user_id = current_user['id']

    # Load the user with the password hash from the DB
    user = get_user_by_id(user_id)
    if not user:
        raise AuthenticationError("User nicht gefunden")

    # Check the current password. Deliberately not a 401: the frontend treats every
    # 401 outside the login as an expired session and logs out - anyone
    # mistyping here would otherwise suddenly land on the login page.
    if not verify_password(request.current_password, user['password_hash']):
        raise ValidationError("Aktuelles Passwort ist falsch")

    # Validate the new password
    if len(request.new_password) < MIN_PASSWORT_LAENGE:
        raise ValidationError(f"Neues Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen lang sein")

    if request.current_password == request.new_password:
        raise ValidationError("Neues Passwort muss sich vom aktuellen unterscheiden")

    # Hash the new password
    new_password_hash = hash_password(request.new_password)

    # Update in DB
    update_user_password(user_id, new_password_hash)

    return ChangePasswordResponse(
        success=True,
        message="Passwort erfolgreich geändert"
    )
