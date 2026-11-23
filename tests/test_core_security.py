"""
core.security: Passwort-Hashes und JWT.

core.security liest JWT_SECRET_KEY beim Import. Die Tests fuer das
Import-Verhalten laden deshalb eine eigene Kopie des Moduls unter fremdem
Namen - das von allen anderen Tests benutzte core.security bleibt unberuehrt.
"""
import hashlib
import importlib.util
from datetime import datetime, timedelta, UTC
from pathlib import Path

import jwt
import pytest

from core import security
from core.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECURITY_DATEI = Path(__file__).resolve().parent.parent / "src" / "core" / "security.py"


def _frische_kopie(name="security_testkopie"):
    """Laedt core/security.py neu, ohne sys.modules['core.security'] zu ersetzen."""
    spec = importlib.util.spec_from_file_location(name, SECURITY_DATEI)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# ===== Passwoerter =====

class TestPasswoerter:
    def test_hin_und_zurueck(self):
        assert verify_password("richtig-geheim", hash_password("richtig-geheim"))

    def test_falsches_passwort(self):
        assert verify_password("falsch", hash_password("richtig-geheim")) is False

    def test_gross_klein_zaehlt(self):
        assert verify_password("Geheim", hash_password("geheim")) is False

    def test_umlaute_und_sonderzeichen(self):
        passwort = "Größe💡 mit Leerzeichen & $"
        assert verify_password(passwort, hash_password(passwort))

    def test_leeres_passwort(self):
        assert verify_password("", hash_password(""))
        assert verify_password("x", hash_password("")) is False

    def test_format_salt_und_hash(self):
        salt, digest = hash_password("geheim").split("$")
        assert len(salt) == 32 and int(salt, 16) >= 0
        assert len(digest) == 64 and int(digest, 16) >= 0

    def test_pbkdf2_mit_100000_iterationen(self):
        salt, digest = hash_password("geheim").split("$")
        erwartet = hashlib.pbkdf2_hmac("sha256", b"geheim", salt.encode(), 100000).hex()
        assert digest == erwartet

    def test_jedes_mal_anderes_salt(self):
        a, b = hash_password("geheim"), hash_password("geheim")
        assert a != b
        assert verify_password("geheim", a) and verify_password("geheim", b)

    def test_klartext_steht_nicht_im_hash(self):
        assert "richtig-geheim" not in hash_password("richtig-geheim")

    @pytest.mark.parametrize("kaputt", [
        "",
        "ohne-trenner",
        "a$b$c",
        "$",
        "salt$",
        None,
        12345,
    ])
    def test_kaputter_hash_ist_einfach_falsch(self, kaputt):
        assert verify_password("geheim", kaputt) is False

    def test_manipulierter_hash(self):
        salt, digest = hash_password("geheim").split("$")
        anders = ("0" if digest[0] != "0" else "1") + digest[1:]
        assert verify_password("geheim", f"{salt}${anders}") is False

    def test_fremdes_salt(self):
        _, digest = hash_password("geheim").split("$")
        assert verify_password("geheim", f"{'0' * 32}${digest}") is False


# ===== JWT =====

class TestToken:
    def test_hin_und_zurueck(self):
        assert decode_access_token(create_access_token(42)) == 42

    def test_inhalt(self):
        payload = jwt.decode(create_access_token(7), SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["user_id"] == 7
        ablauf = datetime.fromtimestamp(payload["exp"], UTC)
        erwartet = datetime.now(UTC) + timedelta(days=security.TOKEN_EXPIRE_DAYS)
        assert abs((ablauf - erwartet).total_seconds()) < 60

    def test_standardlaufzeit_90_tage(self):
        assert security.TOKEN_EXPIRE_DAYS == 90
        assert ALGORITHM == "HS256"

    def test_abgelaufen(self):
        token = jwt.encode(
            {"user_id": 1, "exp": datetime.now(UTC) - timedelta(seconds=1)},
            SECRET_KEY, algorithm=ALGORITHM,
        )
        assert decode_access_token(token) is None

    def test_abgelaufen_ueber_laufzeit(self, monkeypatch):
        monkeypatch.setattr(security, "TOKEN_EXPIRE_DAYS", -1)
        assert decode_access_token(create_access_token(1)) is None

    def test_manipulierte_nutzlast(self):
        kopf, _, signatur = create_access_token(1).split(".")
        fremd = jwt.encode({"user_id": 2, "exp": datetime.now(UTC) + timedelta(days=1)},
                           SECRET_KEY, algorithm=ALGORITHM).split(".")[1]
        assert decode_access_token(f"{kopf}.{fremd}.{signatur}") is None

    def test_manipulierte_signatur(self):
        token = create_access_token(1)
        kopf, nutzlast, signatur = token.split(".")
        anders = ("A" if signatur[0] != "A" else "B") + signatur[1:]
        assert decode_access_token(f"{kopf}.{nutzlast}.{anders}") is None

    def test_fremder_schluessel(self):
        token = jwt.encode({"user_id": 1, "exp": datetime.now(UTC) + timedelta(days=1)},
                           "ein-ganz-anderer-schluessel-der-lang-genug-ist", algorithm=ALGORITHM)
        assert decode_access_token(token) is None

    def test_unsigniertes_token(self):
        token = jwt.encode({"user_id": 1, "exp": datetime.now(UTC) + timedelta(days=1)},
                           key=None, algorithm="none")
        assert decode_access_token(token) is None

    @pytest.mark.parametrize("token", ["", "kein.token", "a.b.c", "nur-text"])
    def test_muell(self, token):
        assert decode_access_token(token) is None

    def test_ohne_user_id(self):
        token = jwt.encode({"exp": datetime.now(UTC) + timedelta(days=1)},
                           SECRET_KEY, algorithm=ALGORITHM)
        assert decode_access_token(token) is None

    def test_ohne_ablauf_bleibt_gueltig(self):
        # PyJWT verlangt exp nicht - dokumentiert das tatsaechliche Verhalten
        token = jwt.encode({"user_id": 5}, SECRET_KEY, algorithm=ALGORITHM)
        assert decode_access_token(token) == 5


# ===== Laden =====

class TestImport:
    def test_ohne_secret_bricht_der_import_ab(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET_KEY")
        with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
            _frische_kopie()

    def test_leeres_secret_bricht_ab(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "")
        with pytest.raises(ValueError):
            _frische_kopie()

    def test_laufzeit_und_algorithmus_aus_umgebung(self, monkeypatch):
        monkeypatch.setenv("JWT_EXPIRATION_DAYS", "7")
        monkeypatch.setenv("JWT_ALGORITHM", "HS512")
        kopie = _frische_kopie()
        assert kopie.TOKEN_EXPIRE_DAYS == 7
        assert kopie.ALGORITHM == "HS512"
        assert kopie.decode_access_token(kopie.create_access_token(3)) == 3
        # Ein HS512-Token wird vom HS256-Modul nicht angenommen
        assert decode_access_token(kopie.create_access_token(3)) is None

    def test_anderes_secret_macht_tokens_ungueltig(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "neues-secret-nach-verlust-der-env-datei")
        kopie = _frische_kopie()
        assert kopie.decode_access_token(create_access_token(1)) is None

    def test_echtes_modul_unberuehrt(self):
        import sys
        assert sys.modules["core.security"] is security
        assert security.SECRET_KEY == SECRET_KEY
