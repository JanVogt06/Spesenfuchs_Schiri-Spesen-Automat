"""
Security Modul - Passwort Hashing + JWT Tokens
Ganz einfach, nur das Noetigste
"""
import os
import hashlib
import hmac
import secrets
import jwt
from datetime import datetime, timedelta, UTC

# JWT Configuration aus .env laden
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY muss in .env gesetzt sein! "
        "Generiere einen mit: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRATION_DAYS", "90"))


def hash_password(password: str) -> str:
    """
    Erstellt sicheren Hash aus Passwort.

    Args:
        password: Klartext-Passwort

    Returns:
        Hash-String (sicher zum Speichern)
    """
    # Generiere zufaelliges Salt
    salt = secrets.token_hex(16)

    # Hash erstellen
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # Iterationen
    )

    # Salt + Hash kombinieren fuer Speicherung
    return f"{salt}${password_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Prueft ob Passwort korrekt ist.

    Args:
        password: Eingegebenes Passwort
        password_hash: Gespeicherter Hash

    Returns:
        True wenn korrekt, False wenn falsch
    """
    try:
        # Trenne Salt und Hash
        salt, stored_hash = password_hash.split('$')

        # Hash neu berechnen mit gleichem Salt
        new_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )

        # Zeitkonstant vergleichen, damit die Laufzeit nichts ueber den Hash verraet
        return hmac.compare_digest(new_hash.hex(), stored_hash)
    except (ValueError, TypeError, AttributeError):
        # Kaputter oder fehlender Hash
        return False


# ===== JWT TOKEN FUNKTIONEN =====

def create_access_token(user_id: int) -> str:
    """
    Erstellt JWT Token fuer User.

    Args:
        user_id: User ID

    Returns:
        JWT Token String
    """
    # Token-Daten
    expire = datetime.now(UTC) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {
        "user_id": user_id,
        "exp": expire  # Ablaufdatum
    }

    # Token erstellen
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_access_token(token: str) -> int:
    """
    Dekodiert JWT Token und gibt user_id zurueck.

    Args:
        token: JWT Token String

    Returns:
        user_id oder None wenn ungueltig
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        return user_id
    except jwt.ExpiredSignatureError:
        # Token abgelaufen
        return None
    except jwt.InvalidTokenError:
        # Token ungueltig
        return None