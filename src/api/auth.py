"""
Authentication Endpoints - Register und Login mit JWT + DFB-Credentials
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

# Gilt fuer Registrierung und Passwortwechsel gleichermassen. Das Frontend
# prueft dasselbe, aber wer die API direkt aufruft, umginge es sonst.
MIN_PASSWORT_LAENGE = 8


# ===== Request/Response Models =====

class RegisterRequest(BaseModel):
    """Register-Anfrage"""
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """Login-Anfrage"""
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Auth-Antwort mit Token"""
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str


class UserInfo(BaseModel):
    """User-Informationen"""
    user_id: int
    email: str
    has_dfb_credentials: bool
    # Seit wann DFBnet die gespeicherten Zugangsdaten ablehnt (ISO, UTC)
    dfb_login_abgelehnt_seit: Optional[str] = None


class DFBCredentialsRequest(BaseModel):
    """DFB-Credentials Anfrage"""
    dfb_username: str
    dfb_password: str


class DFBCredentialsResponse(BaseModel):
    """DFB-Credentials Antwort"""
    success: bool
    message: str

class ChangePasswordRequest(BaseModel):
    """Passwort-Ändern-Anfrage"""
    current_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    """Passwort-Ändern-Antwort"""
    success: bool
    message: str


# ===== Dependency: Get Current User =====

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Extrahiert User aus JWT Token.

    Wird als Dependency verwendet: current_user = Depends(get_current_user)
    """
    if not authorization:
        raise AuthenticationError("Token fehlt")

    # Token aus "Bearer TOKEN" extrahieren
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise AuthenticationError("Ungültiges Token-Format")
    except ValueError:
        raise AuthenticationError("Ungültiges Token-Format")

    # Token dekodieren
    user_id = decode_access_token(token)
    if not user_id:
        raise AuthenticationError("Token ungültig oder abgelaufen")

    # User aus DB holen
    user = get_user_by_id(user_id)
    if not user:
        raise AuthenticationError("User nicht gefunden")

    return user


# ===== Endpoints =====

@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(request: RegisterRequest):
    """
    Registriert neuen User und gibt Token zurueck.

    - Prueft ob Email schon existiert
    - Hasht Passwort sicher
    - Erstellt User in DB
    - Gibt JWT Token zurueck
    """
    if len(request.password) < MIN_PASSWORT_LAENGE:
        raise ValidationError(f"Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen lang sein")

    # Klein geschrieben gespeichert; get_user_by_email vergleicht ohnehin
    # ohne Ruecksicht auf Gross-/Kleinschreibung.
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
    Login mit Email und Passwort, gibt Token zurueck.

    Nach MAX_FEHLVERSUCHE falschen Passwoertern hintereinander ist die
    Adresse SPERRDAUER_MINUTEN lang gesperrt - auch fuer das richtige
    Passwort, sonst liesse sich waehrend der Sperre weiter raten.
    """
    if bis := gesperrt_bis(request.email):
        minuten = math.ceil((bis - datetime.now(UTC)).total_seconds() / 60)
        raise LoginGesperrtError(max(minuten, 1))

    user = get_user_by_email(request.email)

    # Unbekannte Adresse und falsches Passwort zaehlen gleich, damit weder
    # Meldung noch Sperre verraten, ob es ein Konto gibt.
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

    # Erstelle Token
    token = create_access_token(user['id'])

    # Login protokollieren (best-effort, darf den Login nie blockieren)
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
    Gibt Informationen ueber aktuell eingeloggten User zurueck.
    Benoetigt Token im Authorization Header.
    """
    # Pruefe ob User DFB-Credentials gespeichert hat
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
    Speichert DFB-Credentials verschluesselt fuer den User.

    Diese Credentials werden automatisch beim Generieren verwendet,
    sodass der User sie nicht jedes Mal eingeben muss.
    """
    user_id = current_user['id']

    # Validierung
    if not request.dfb_username or not request.dfb_password:
        raise ValidationError("DFB Username und Passwort müssen angegeben werden")

    # Verschluesseln
    encrypted_username = encrypt_credential(request.dfb_username)
    encrypted_password = encrypt_credential(request.dfb_password)

    # Gehoert der neue Zugang noch zum selben DFBnet-Konto? Muss VOR dem
    # Ueberschreiben geprueft werden.
    try:
        bisher = get_dfb_credentials(user_id)
        gleiches_konto = bool(bisher) and decrypt_credential(
            bisher['dfb_username_encrypted']
        ) == request.dfb_username
    except Exception:
        # Laesst sich der alte Benutzername nicht mehr entschluesseln, wird im
        # Zweifel geloescht: lieber ein leerer Reiter als fremde Personendaten.
        gleiches_konto = False

    # In DB speichern
    update_dfb_credentials(user_id, encrypted_username, encrypted_password)

    # Die gespeicherten Stammdaten gehoeren zum bisherigen DFBnet-Konto. Zeigt
    # jemand die App auf ein anderes Konto, stuenden dort bis zum naechsten
    # erfolgreichen Abruf Name, Anschrift und Geburtsdatum einer anderen
    # Person - also weg damit.
    #
    # Ein reiner Passwortwechsel laesst sie dagegen stehen. DFBnet erzwingt den
    # regelmaessig; wuerde er die Stammdaten mitnehmen, waere der Reiter danach
    # jedes Mal bis zum naechsten Nachtlauf leer.
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
    Prueft ob User DFB-Credentials gespeichert hat.
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
    Ändert das Passwort des eingeloggten Users.

    - Prüft ob aktuelles Passwort korrekt ist
    - Validiert neues Passwort (Mindestlänge)
    - Hasht und speichert neues Passwort
    """
    user_id = current_user['id']

    # Hole User mit Passwort-Hash aus DB
    user = get_user_by_id(user_id)
    if not user:
        raise AuthenticationError("User nicht gefunden")

    # Prüfe aktuelles Passwort. Bewusst kein 401: das Frontend wertet jeden
    # 401 ausserhalb des Logins als abgelaufene Sitzung und meldet ab - wer
    # sich hier vertippt, stuende sonst unvermittelt auf der Login-Seite.
    if not verify_password(request.current_password, user['password_hash']):
        raise ValidationError("Aktuelles Passwort ist falsch")

    # Validiere neues Passwort
    if len(request.new_password) < MIN_PASSWORT_LAENGE:
        raise ValidationError(f"Neues Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen lang sein")

    if request.current_password == request.new_password:
        raise ValidationError("Neues Passwort muss sich vom aktuellen unterscheiden")

    # Hash neues Passwort
    new_password_hash = hash_password(request.new_password)

    # Update in DB
    update_user_password(user_id, new_password_hash)

    return ChangePasswordResponse(
        success=True,
        message="Passwort erfolgreich geändert"
    )
