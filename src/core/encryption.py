"""
Encryption module - encryption for DFB credentials
Uses Fernet (symmetric encryption)
"""
import os
from cryptography.fernet import Fernet


def get_encryption_key() -> bytes:
    """
    Reads the encryption key from .env.

    Returns:
        Encryption key as bytes
    """
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise ValueError(
            "ENCRYPTION_KEY muss in .env gesetzt sein! "
            "Generiere einen mit: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return key.encode()


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypts a string (e.g. a password).

    Args:
        plaintext: Plain text

    Returns:
        Encrypted string (base64)
    """
    if not plaintext:
        return ""

    key = get_encryption_key()
    fernet = Fernet(key)

    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()


def decrypt_credential(encrypted: str) -> str:
    """
    Decrypts a string.

    Args:
        encrypted: Encrypted string (base64)

    Returns:
        Plain text
    """
    if not encrypted:
        return ""

    key = get_encryption_key()
    fernet = Fernet(key)

    decrypted = fernet.decrypt(encrypted.encode())
    return decrypted.decode()