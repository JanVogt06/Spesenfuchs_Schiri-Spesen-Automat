"""
core.config: where data and secrets live, and the creation of the secrets on
the very first start.

PROJECT_ROOT is redirected to a throwaway directory so that the real project
(and certainly not data/) is never touched.
"""
import os
import stat

import pytest
from cryptography.fernet import Fernet

from core import config
from core.config import (
    _bootstrap_secrets,
    _prefer_existing,
    get_data_dir,
    get_db_path,
    get_env_file,
    get_output_dir,
    load_environment,
)

PFAD_VARIABLEN = ("DATA_DIR", "ENV_FILE", "DATABASE_PATH", "OUTPUT_DIR")


def _env_weg(monkeypatch, name):
    """Removes a variable such that monkeypatch safely restores it afterwards."""
    monkeypatch.setenv(name, "platzhalter")
    monkeypatch.delenv(name)


@pytest.fixture
def projekt(tmp_path, monkeypatch):
    """An empty project directory, without path variables."""
    root = tmp_path / "projekt"
    root.mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", root)
    for name in PFAD_VARIABLEN:
        _env_weg(monkeypatch, name)
    return root


@pytest.fixture
def ohne_secrets(monkeypatch):
    for name in ("JWT_SECRET_KEY", "ENCRYPTION_KEY"):
        _env_weg(monkeypatch, name)


# ===== Paths =====

class TestDatenverzeichnis:
    def test_standard_ist_data_im_projekt(self, projekt):
        assert get_data_dir() == projekt / "data"

    def test_data_dir_aus_umgebung(self, projekt, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "anderswo"))
        assert get_data_dir() == tmp_path / "anderswo"

    def test_leeres_data_dir_zaehlt_nicht(self, projekt, monkeypatch):
        monkeypatch.setenv("DATA_DIR", "")
        assert get_data_dir() == projekt / "data"


class TestPreferExisting:
    def test_neuer_ort_vorhanden(self, tmp_path):
        (tmp_path / "neu").write_text("x")
        (tmp_path / "alt").write_text("x")
        assert _prefer_existing(tmp_path / "neu", tmp_path / "alt") == tmp_path / "neu"

    def test_nur_alter_ort_vorhanden(self, tmp_path):
        (tmp_path / "alt").write_text("x")
        assert _prefer_existing(tmp_path / "neu", tmp_path / "alt") == tmp_path / "alt"

    def test_keiner_vorhanden(self, tmp_path):
        assert _prefer_existing(tmp_path / "neu", tmp_path / "alt") == tmp_path / "neu"

    def test_gleicher_pfad(self, tmp_path):
        (tmp_path / "x").write_text("x")
        assert _prefer_existing(tmp_path / "x", tmp_path / "x") == tmp_path / "x"


class TestEnvFile:
    def test_env_file_aus_umgebung_gewinnt(self, projekt, monkeypatch, tmp_path):
        (projekt / ".env").write_text("")
        monkeypatch.setenv("ENV_FILE", str(tmp_path / "eigene.env"))
        assert get_env_file() == tmp_path / "eigene.env"

    def test_standard_im_datenverzeichnis(self, projekt):
        assert get_env_file() == projekt / "data" / ".env"

    def test_alte_env_im_projekt_wird_weiterbenutzt(self, projekt):
        (projekt / ".env").write_text("")
        assert get_env_file() == projekt / ".env"

    def test_neue_env_gewinnt_gegen_alte(self, projekt):
        (projekt / ".env").write_text("")
        (projekt / "data").mkdir()
        (projekt / "data" / ".env").write_text("")
        assert get_env_file() == projekt / "data" / ".env"

    def test_folgt_data_dir(self, projekt, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
        assert get_env_file() == tmp_path / "d" / ".env"


class TestDbPath:
    def test_database_path_aus_umgebung(self, projekt, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "x.db"))
        assert get_db_path() == tmp_path / "x.db"

    def test_standard(self, projekt):
        assert get_db_path() == projekt / "data" / "app.db"

    def test_alte_datenbank_im_projekt(self, projekt):
        (projekt / "app.db").write_bytes(b"")
        assert get_db_path() == projekt / "app.db"

    def test_neue_datenbank_gewinnt(self, projekt):
        (projekt / "app.db").write_bytes(b"")
        (projekt / "data").mkdir()
        (projekt / "data" / "app.db").write_bytes(b"")
        assert get_db_path() == projekt / "data" / "app.db"


class TestOutputDir:
    def test_output_dir_aus_umgebung(self, projekt, monkeypatch, tmp_path):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "o"))
        assert get_output_dir() == tmp_path / "o"

    def test_standard(self, projekt):
        assert get_output_dir() == projekt / "data" / "output"

    def test_leerer_alter_ordner_zaehlt_nicht(self, projekt):
        (projekt / "output").mkdir()
        assert get_output_dir() == projekt / "data" / "output"

    def test_gefuellter_alter_ordner(self, projekt):
        (projekt / "output").mkdir()
        (projekt / "output" / "session1").mkdir()
        assert get_output_dir() == projekt / "output"

    def test_neuer_ordner_gewinnt_auch_gegen_gefuellten_alten(self, projekt):
        (projekt / "output").mkdir()
        (projekt / "output" / "session1").mkdir()
        (projekt / "data" / "output").mkdir(parents=True)
        assert get_output_dir() == projekt / "data" / "output"

    def test_alte_datei_statt_ordner_zaehlt_nicht(self, projekt):
        (projekt / "output").write_text("kein ordner")
        assert get_output_dir() == projekt / "data" / "output"


# ===== Secrets on first start =====

def _lies_env(pfad):
    werte = {}
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if zeile and not zeile.startswith("#") and "=" in zeile:
            name, wert = zeile.split("=", 1)
            werte[name] = wert
    return werte


class TestBootstrapSecrets:
    def test_legt_neue_datei_mit_0600_an(self, tmp_path, ohne_secrets):
        env_file = tmp_path / "data" / ".env"
        _bootstrap_secrets(env_file)

        assert env_file.exists()
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    def test_erzeugt_beide_secrets(self, tmp_path, ohne_secrets):
        env_file = tmp_path / ".env"
        _bootstrap_secrets(env_file)

        werte = _lies_env(env_file)
        assert set(werte) == {"JWT_SECRET_KEY", "ENCRYPTION_KEY"}
        assert len(werte["JWT_SECRET_KEY"]) >= 32
        # A valid Fernet key
        Fernet(werte["ENCRYPTION_KEY"].encode())

    def test_setzt_die_secrets_in_die_umgebung(self, tmp_path, ohne_secrets):
        env_file = tmp_path / ".env"
        _bootstrap_secrets(env_file)
        werte = _lies_env(env_file)
        assert os.environ["JWT_SECRET_KEY"] == werte["JWT_SECRET_KEY"]
        assert os.environ["ENCRYPTION_KEY"] == werte["ENCRYPTION_KEY"]

    def test_warnung_im_kopf(self, tmp_path, ohne_secrets):
        env_file = tmp_path / ".env"
        _bootstrap_secrets(env_file)
        assert env_file.read_text(encoding="utf-8").startswith("# Automatisch beim ersten Start erzeugt.")

    def test_jedes_mal_andere_secrets(self, tmp_path, ohne_secrets, monkeypatch):
        _bootstrap_secrets(tmp_path / "a.env")
        for name in ("JWT_SECRET_KEY", "ENCRYPTION_KEY"):
            monkeypatch.delenv(name)
        _bootstrap_secrets(tmp_path / "b.env")
        assert _lies_env(tmp_path / "a.env") != _lies_env(tmp_path / "b.env")

    def test_vorhandene_datei_wird_nie_angefasst(self, tmp_path, ohne_secrets):
        env_file = tmp_path / ".env"
        env_file.write_text("ENCRYPTION_KEY=alt\n", encoding="utf-8")
        env_file.chmod(0o644)

        _bootstrap_secrets(env_file)

        assert env_file.read_text(encoding="utf-8") == "ENCRYPTION_KEY=alt\n"
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o644
        assert "JWT_SECRET_KEY" not in os.environ

    def test_vorhandene_leere_datei_wird_nie_angefasst(self, tmp_path, ohne_secrets):
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        _bootstrap_secrets(env_file)
        assert env_file.read_text(encoding="utf-8") == ""

    def test_alle_secrets_gesetzt_keine_datei(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "aus-der-umgebung")
        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        env_file = tmp_path / ".env"
        _bootstrap_secrets(env_file)
        assert not env_file.exists()

    def test_nur_fehlende_secrets_werden_erzeugt(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "aus-der-umgebung")
        _env_weg(monkeypatch, "ENCRYPTION_KEY")
        env_file = tmp_path / ".env"

        _bootstrap_secrets(env_file)

        assert set(_lies_env(env_file)) == {"ENCRYPTION_KEY"}
        assert os.environ["JWT_SECRET_KEY"] == "aus-der-umgebung"

    def test_gleichzeitiger_start_liest_die_fremde_datei(self, tmp_path, ohne_secrets, monkeypatch):
        # A second process created the file between exists() and os.open
        env_file = tmp_path / ".env"
        fremd = "JWT_SECRET_KEY=vom-anderen-prozess\nENCRYPTION_KEY=auch-von-dort\n"

        def os_open(pfad, flags, mode=0o777):
            assert flags & os.O_EXCL
            env_file.write_text(fremd, encoding="utf-8")
            raise FileExistsError(pfad)

        with monkeypatch.context() as m:
            m.setattr(config.os, "open", os_open)
            _bootstrap_secrets(env_file)

        assert env_file.read_text(encoding="utf-8") == fremd
        assert os.environ["JWT_SECRET_KEY"] == "vom-anderen-prozess"
        assert os.environ["ENCRYPTION_KEY"] == "auch-von-dort"

    def test_nicht_beschreibbar_wirft_nicht(self, tmp_path, ohne_secrets, monkeypatch):
        def os_open(*args, **kwargs):
            raise PermissionError("schreibgeschuetzt")

        monkeypatch.setattr(config.os, "open", os_open)
        env_file = tmp_path / ".env"
        _bootstrap_secrets(env_file)
        assert not env_file.exists()
        assert "JWT_SECRET_KEY" not in os.environ


class TestLoadEnvironment:
    def test_laedt_datei_und_gibt_pfad_zurueck(self, tmp_path, monkeypatch):
        env_file = tmp_path / "eigene.env"
        env_file.write_text("SPESENFUCHS_TEST_WERT=aus-der-datei\n", encoding="utf-8")
        monkeypatch.setenv("ENV_FILE", str(env_file))
        _env_weg(monkeypatch, "SPESENFUCHS_TEST_WERT")

        assert load_environment() == env_file
        assert os.environ["SPESENFUCHS_TEST_WERT"] == "aus-der-datei"

    def test_umgebung_gewinnt_gegen_datei(self, tmp_path, monkeypatch):
        env_file = tmp_path / "eigene.env"
        env_file.write_text("SPESENFUCHS_TEST_WERT=aus-der-datei\n", encoding="utf-8")
        monkeypatch.setenv("ENV_FILE", str(env_file))
        monkeypatch.setenv("SPESENFUCHS_TEST_WERT", "aus-der-umgebung")

        load_environment()
        assert os.environ["SPESENFUCHS_TEST_WERT"] == "aus-der-umgebung"

    def test_erster_start_legt_secrets_an(self, tmp_path, monkeypatch, ohne_secrets):
        env_file = tmp_path / "neu" / ".env"
        monkeypatch.setenv("ENV_FILE", str(env_file))

        load_environment()

        assert set(_lies_env(env_file)) == {"JWT_SECRET_KEY", "ENCRYPTION_KEY"}
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    def test_secrets_aus_vorhandener_datei_werden_geladen(self, tmp_path, monkeypatch, ohne_secrets):
        env_file = tmp_path / ".env"
        env_file.write_text("JWT_SECRET_KEY=gespeichert\nENCRYPTION_KEY=auch\n", encoding="utf-8")
        monkeypatch.setenv("ENV_FILE", str(env_file))

        load_environment()

        assert os.environ["JWT_SECRET_KEY"] == "gespeichert"
        assert env_file.read_text(encoding="utf-8") == "JWT_SECRET_KEY=gespeichert\nENCRYPTION_KEY=auch\n"
