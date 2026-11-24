"""
Security module - password hashing + JWT tokens
Very simple, only the bare minimum
"""
import os
import hashlib
import hmac
import secrets
import jwt
from datetime import datetime, timedelta, UTC

# Load JWT configuration from .env
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
    Creates a secure hash from a password.

    Args:
        password: Plain-text password

    Returns:
        Hash string (safe to store)
    """
    # Generate a random salt
    salt = secrets.token_hex(16)

    # Create the hash
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )

    # Combine salt + hash for storage
    return f"{salt}${password_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Checks whether a password is correct.

    Args:
        password: Entered password
        password_hash: Stored hash

    Returns:
        True if correct, False if wrong
    """
    try:
        # Split salt and hash
        salt, stored_hash = password_hash.split('$')

        # Recompute the hash with the same salt
        new_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )

        # Compare in constant time so the runtime reveals nothing about the hash
        return hmac.compare_digest(new_hash.hex(), stored_hash)
    except (ValueError, TypeError, AttributeError):
        # Corrupt or missing hash
        return False


# ===== JWT TOKEN FUNCTIONS =====

def create_access_token(user_id: int) -> str:
    """
    Creates a JWT token for a user.

    Args:
        user_id: User ID

    Returns:
        JWT token string
    """
    # Token data
    expire = datetime.now(UTC) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {
        "user_id": user_id,
        "exp": expire  # expiry date
    }

    # Create the token
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_access_token(token: str) -> int:
    """
    Decodes a JWT token and returns the user_id.

    Args:
        token: JWT token string

    Returns:
        user_id, or None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        return user_id
    except jwt.ExpiredSignatureError:
        # Token expired
        return None
    except jwt.InvalidTokenError:
        # Token invalid
        return None