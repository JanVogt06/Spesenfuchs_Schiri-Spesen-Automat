"""
utils.logger: Konsole plus Protokolldatei unter LOG_FILE.

Der Datei-Handler ist ein Prozess-Singleton. Tests, die ihn neu anlegen
lassen, setzen ihn per monkeypatch zurueck und schliessen ihren eigenen
Handler wieder - die anderen Tests schreiben weiter in den urspruenglichen.
"""
import logging
import os
import uuid
from logging.handlers import RotatingFileHandler, WatchedFileHandler
from pathlib import Path

import pytest

from utils import logger as logmodul
from utils.logger import setup_logger


def _eindeutiger_name():
    return f"test_logger_{uuid.uuid4().hex}"


@pytest.fixture
def eigener_handler(monkeypatch):
    """Sorgt dafuer, dass der naechste Aufruf einen neuen Datei-Handler anlegt."""
    monkeypatch.setattr(logmodul, "_datei_handler", None)
    erzeugt = []
    yield erzeugt
    handler = logmodul._datei_handler
    if handler:
        handler.close()
    for name in erzeugt:
        logging.getLogger(name).handlers.clear()


class TestPfad:
    def test_log_file_gewinnt(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "x.log"))
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        assert logmodul._log_datei() == tmp_path / "x.log"

    def test_sonst_unter_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LOG_FILE")
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        assert logmodul._log_datei() == tmp_path / "data" / "logs" / "spesenfuchs.log"

    def test_ohne_beides_im_projekt(self, monkeypatch):
        monkeypatch.delenv("LOG_FILE")
        monkeypatch.delenv("DATA_DIR")
        projekt = Path(logmodul.__file__).resolve().parent.parent.parent
        assert logmodul._log_datei() == projekt / "data" / "logs" / "spesenfuchs.log"


class TestSchreiben:
    def test_schreibt_in_die_testdatei(self):
        name = _eindeutiger_name()
        log = setup_logger(name)
        marke = f"marke-{uuid.uuid4().hex}"
        log.info(marke)

        datei_handler = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
        assert len(datei_handler) == 1
        datei_handler[0].flush()
        pfad = Path(datei_handler[0].baseFilename)

        # Niemals ins echte data/ des Projekts
        projekt_data = Path(logmodul.__file__).resolve().parent.parent.parent / "data"
        assert projekt_data not in pfad.parents
        assert marke in pfad.read_text(encoding="utf-8")
        logging.getLogger(name).handlers.clear()

    def test_neue_datei_unter_log_file(self, monkeypatch, tmp_path, eigener_handler):
        ziel = tmp_path / "unter" / "ordner" / "app.log"
        monkeypatch.setenv("LOG_FILE", str(ziel))
        name = _eindeutiger_name()
        eigener_handler.append(name)

        log = setup_logger(name)
        log.warning("hallo datei")
        log.debug("zu leise")
        logmodul._datei_handler.flush()

        inhalt = ziel.read_text(encoding="utf-8")
        assert "WARNING - hallo datei" in inhalt
        assert "zu leise" not in inhalt
        assert inhalt.startswith("[")

    def test_format(self, monkeypatch, tmp_path, eigener_handler):
        ziel = tmp_path / "app.log"
        monkeypatch.setenv("LOG_FILE", str(ziel))
        name = _eindeutiger_name()
        eigener_handler.append(name)

        setup_logger(name).error("kaputt")
        logmodul._datei_handler.flush()

        zeile = ziel.read_text(encoding="utf-8").strip()
        import re
        assert re.fullmatch(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ERROR - kaputt", zeile)

    def test_auch_auf_die_konsole(self, capsys):
        name = _eindeutiger_name()
        setup_logger(name).info("auf stdout")
        assert "INFO - auf stdout" in capsys.readouterr().out
        logging.getLogger(name).handlers.clear()


class TestHandler:
    def test_keine_doppelten_handler(self):
        name = _eindeutiger_name()
        a = setup_logger(name)
        anzahl = len(a.handlers)
        b = setup_logger(name)
        assert a is b
        assert len(b.handlers) == anzahl == 2
        logging.getLogger(name).handlers.clear()

    def test_alle_logger_teilen_einen_datei_handler(self):
        a, b = setup_logger(_eindeutiger_name()), setup_logger(_eindeutiger_name())
        datei_a = [h for h in a.handlers if isinstance(h, logging.FileHandler)]
        datei_b = [h for h in b.handlers if isinstance(h, logging.FileHandler)]
        assert datei_a[0] is datei_b[0]
        a.handlers.clear()
        b.handlers.clear()

    def test_level(self):
        name = _eindeutiger_name()
        log = setup_logger(name, level=logging.DEBUG)
        assert log.level == logging.DEBUG
        logging.getLogger(name).handlers.clear()

    def test_hauptprozess_rotiert(self, monkeypatch, tmp_path, eigener_handler):
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "a.log"))
        handler = logmodul._hole_datei_handler()
        assert isinstance(handler, RotatingFileHandler)
        assert handler.maxBytes == 5 * 1024 * 1024
        assert handler.backupCount == 4

    def test_kindprozess_haengt_nur_an(self, monkeypatch, tmp_path, eigener_handler):
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "a.log"))
        monkeypatch.setattr(logmodul.multiprocessing, "parent_process", lambda: object())
        handler = logmodul._hole_datei_handler()
        assert isinstance(handler, WatchedFileHandler)
        assert not isinstance(handler, RotatingFileHandler)

    def test_handler_wird_nur_einmal_angelegt(self, monkeypatch, tmp_path, eigener_handler):
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "a.log"))
        erster = logmodul._hole_datei_handler()
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "b.log"))
        assert logmodul._hole_datei_handler() is erster

    def test_nicht_beschreibbar_nur_konsole(self, monkeypatch, tmp_path, eigener_handler, capsys):
        # Ein Ordner kann nicht unter einer Datei angelegt werden
        sperre = tmp_path / "datei"
        sperre.write_text("")
        monkeypatch.setenv("LOG_FILE", str(sperre / "logs" / "x.log"))

        assert logmodul._hole_datei_handler() is None
        assert logmodul._datei_handler is False
        assert "nicht beschreibbar" in capsys.readouterr().err

        # Kein zweiter Versuch
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "geht.log"))
        assert logmodul._hole_datei_handler() is None

        name = _eindeutiger_name()
        eigener_handler.append(name)
        log = setup_logger(name)
        assert len(log.handlers) == 1
        assert not any(isinstance(h, logging.FileHandler) for h in log.handlers)

    def test_testsitzung_schreibt_nicht_ins_projekt(self):
        log_file = Path(os.environ["LOG_FILE"])
        projekt = Path(logmodul.__file__).resolve().parent.parent.parent
        assert projekt not in log_file.parents
