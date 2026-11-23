"""core.encryption: Fernet-Verschluesselung der DFBnet-Zugangsdaten."""
import pytest
from cryptography.fernet import Fernet, InvalidToken

from core.encryption import decrypt_credential, encrypt_credential, get_encryption_key


class TestSchluessel:
    def test_aus_der_umgebung(self, monkeypatch):
        schluessel = Fernet.generate_key().decode()
        monkeypatch.setenv("ENCRYPTION_KEY", schluessel)
        assert get_encryption_key() == schluessel.encode()

    def test_fehlt(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY")
        with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
            get_encryption_key()

    def test_leer(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "")
        with pytest.raises(ValueError):
            get_encryption_key()

    def test_wird_bei_jedem_aufruf_gelesen(self, monkeypatch):
        # Anders als JWT_SECRET_KEY nicht beim Import eingefroren
        monkeypatch.setenv("ENCRYPTION_KEY", "eins")
        assert get_encryption_key() == b"eins"
        monkeypatch.setenv("ENCRYPTION_KEY", "zwei")
        assert get_encryption_key() == b"zwei"


class TestVerschluesselung:
    def test_hin_und_zurueck(self):
        assert decrypt_credential(encrypt_credential("dfb-passwort")) == "dfb-passwort"

    def test_umlaute_und_sonderzeichen(self):
        text = "Pässwörd mit €, ß und 💡"
        assert decrypt_credential(encrypt_credential(text)) == text

    def test_klartext_steht_nicht_im_ergebnis(self):
        assert "dfb-passwort" not in encrypt_credential("dfb-passwort")

    def test_ergebnis_ist_ein_fernet_token(self, monkeypatch):
        schluessel = Fernet.generate_key()
        monkeypatch.setenv("ENCRYPTION_KEY", schluessel.decode())
        assert Fernet(schluessel).decrypt(encrypt_credential("x").encode()) == b"x"

    def test_jedes_mal_anders(self):
        assert encrypt_credential("gleich") != encrypt_credential("gleich")

    def test_leer_bleibt_leer(self):
        assert encrypt_credential("") == ""
        assert decrypt_credential("") == ""

    def test_none_bleibt_leer(self):
        assert encrypt_credential(None) == ""
        assert decrypt_credential(None) == ""

    def test_leer_braucht_keinen_schluessel(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY")
        assert encrypt_credential("") == ""
        assert decrypt_credential("") == ""

    def test_falscher_schluessel(self, monkeypatch):
        verschluesselt = encrypt_credential("dfb-passwort")
        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        with pytest.raises(InvalidToken):
            decrypt_credential(verschluesselt)

    def test_manipulierter_text(self):
        verschluesselt = encrypt_credential("dfb-passwort")
        mitte = len(verschluesselt) // 2
        anders = verschluesselt[:mitte] + ("A" if verschluesselt[mitte] != "A" else "B") + verschluesselt[mitte + 1:]
        with pytest.raises(InvalidToken):
            decrypt_credential(anders)

    def test_kein_token(self):
        with pytest.raises(InvalidToken):
            decrypt_credential("das-ist-kein-token")

    def test_ungueltiger_schluessel(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "zu-kurz")
        with pytest.raises(ValueError):
            encrypt_credential("x")

    def test_verschluesseln_ohne_schluessel(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY")
        with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
            encrypt_credential("x")
