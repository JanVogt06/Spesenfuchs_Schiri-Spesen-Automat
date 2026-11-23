"""
PDF-Konvertierung ohne LibreOffice: soffice-Suche und subprocess.run sind
ersetzt. Der Ersatz fuer soffice legt die PDFs so an, wie es das echte
Programm taete - neben die Eingabe ins --outdir.
"""
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils import pdf_converter
from utils.pdf_converter import (
    MAX_CONVERT_SECONDS,
    convert_docx_bytes_to_pdf,
    convert_docx_files_to_pdf,
)


class FalschesSoffice:
    """Ersatz fuer subprocess.run, merkt sich die Aufrufe."""

    def __init__(self, returncode=0, erzeugen=None, ausnahme=None, stderr=""):
        self.returncode = returncode
        # None: fuer jede Eingabe eine PDF; sonst nur fuer diese Indizes
        self.erzeugen = erzeugen
        self.ausnahme = ausnahme
        self.stderr = stderr
        self.aufrufe = []

    def __call__(self, befehl, **kwargs):
        self.aufrufe.append((befehl, kwargs))
        if self.ausnahme:
            raise self.ausnahme

        outdir = Path(befehl[befehl.index("--outdir") + 1])
        eingaben = befehl[befehl.index("--outdir") + 2:]
        for index, eingabe in enumerate(eingaben):
            if self.erzeugen is None or index in self.erzeugen:
                (outdir / Path(eingabe).with_suffix(".pdf").name).write_bytes(
                    b"%PDF-" + Path(eingabe).read_bytes()
                )
        return SimpleNamespace(returncode=self.returncode, stdout="", stderr=self.stderr)


@pytest.fixture
def soffice_da(monkeypatch):
    monkeypatch.setattr(pdf_converter, "_find_soffice", lambda: "/usr/bin/soffice-test")


@pytest.fixture
def temp_dirs(monkeypatch, tmp_path):
    """Leitet mkdtemp in tmp_path um, damit sich das Aufraeumen pruefen laesst."""
    angelegt = []
    zaehler = iter(range(1000))

    def mkdtemp(prefix=""):
        pfad = tmp_path / f"{prefix}{next(zaehler)}"
        pfad.mkdir()
        angelegt.append(pfad)
        return str(pfad)

    monkeypatch.setattr(pdf_converter.tempfile, "mkdtemp", mkdtemp)
    return angelegt


# ===== soffice finden =====

class TestSofficeFinden:
    def test_nimmt_ersten_treffer_im_path(self, monkeypatch):
        monkeypatch.setattr(pdf_converter.shutil, "which",
                            lambda name: "/usr/bin/soffice" if name == "soffice" else None)
        assert pdf_converter._find_soffice() == "soffice"

    def test_faellt_auf_libreoffice_zurueck(self, monkeypatch):
        monkeypatch.setattr(pdf_converter.shutil, "which",
                            lambda name: "/usr/bin/libreoffice" if name == "libreoffice" else None)
        assert pdf_converter._find_soffice() == "libreoffice"

    def test_absoluter_pfad_wenn_vorhanden(self, monkeypatch, tmp_path):
        programm = tmp_path / "soffice"
        programm.write_text("")
        monkeypatch.setattr(pdf_converter.shutil, "which", lambda name: None)
        monkeypatch.setattr(pdf_converter, "_SOFFICE_CANDIDATES", ["soffice", str(programm)])
        assert pdf_converter._find_soffice() == str(programm)

    def test_fehlt_ganz(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pdf_converter.shutil, "which", lambda name: None)
        monkeypatch.setattr(pdf_converter, "_SOFFICE_CANDIDATES",
                            ["soffice", "libreoffice", str(tmp_path / "gibtsnicht")])
        with pytest.raises(FileNotFoundError, match="LibreOffice"):
            pdf_converter._find_soffice()


# ===== Dateien =====

class TestDateienKonvertieren:
    def _dateien(self, verzeichnis, anzahl):
        pfade = []
        for i in range(anzahl):
            pfad = verzeichnis / f"dok{i}.docx"
            pfad.write_bytes(f"inhalt{i}".encode())
            pfade.append(pfad)
        return pfade

    def test_leere_liste_ohne_aufruf(self, monkeypatch):
        aufruf = FalschesSoffice()
        monkeypatch.setattr(pdf_converter.subprocess, "run", aufruf)
        assert convert_docx_files_to_pdf([]) == {}
        assert aufruf.aufrufe == []

    def test_erfolg(self, monkeypatch, tmp_path, soffice_da):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice())
        pfade = self._dateien(tmp_path, 2)
        assert convert_docx_files_to_pdf(pfade) == {pfade[0]: True, pfade[1]: True}

    def test_ein_aufruf_fuer_alle_dateien(self, monkeypatch, tmp_path, soffice_da):
        aufruf = FalschesSoffice()
        monkeypatch.setattr(pdf_converter.subprocess, "run", aufruf)
        pfade = self._dateien(tmp_path, 3)

        convert_docx_files_to_pdf(pfade)

        assert len(aufruf.aufrufe) == 1
        befehl, kwargs = aufruf.aufrufe[0]
        assert befehl[0] == "/usr/bin/soffice-test"
        assert "--headless" in befehl
        assert befehl[befehl.index("--convert-to") + 1] == "pdf"
        assert befehl[befehl.index("--outdir") + 1] == str(tmp_path)
        assert befehl[-3:] == [str(p) for p in pfade]
        assert kwargs["capture_output"] is True

    def test_eigenes_profil_wird_aufgeraeumt(self, monkeypatch, tmp_path, soffice_da, temp_dirs):
        aufruf = FalschesSoffice()
        monkeypatch.setattr(pdf_converter.subprocess, "run", aufruf)
        eingabe = tmp_path / "eingabe"
        eingabe.mkdir()

        convert_docx_files_to_pdf(self._dateien(eingabe, 1))

        befehl, _ = aufruf.aufrufe[0]
        profil = [a for a in befehl if a.startswith("-env:UserInstallation=file://")]
        assert len(profil) == 1
        profil_pfad = Path(profil[0].removeprefix("-env:UserInstallation=file://"))
        assert profil_pfad in temp_dirs
        assert not profil_pfad.exists()

    @pytest.mark.parametrize("anzahl, erwartet", [
        (1, 120),
        (2, 240),
        (3, MAX_CONVERT_SECONDS),
        (50, MAX_CONVERT_SECONDS),
    ])
    def test_zeitlimit(self, monkeypatch, tmp_path, soffice_da, anzahl, erwartet):
        aufruf = FalschesSoffice()
        monkeypatch.setattr(pdf_converter.subprocess, "run", aufruf)
        convert_docx_files_to_pdf(self._dateien(tmp_path, anzahl))
        assert aufruf.aufrufe[0][1]["timeout"] == erwartet

    def test_fehlercode_ohne_pdf(self, monkeypatch, tmp_path, soffice_da):
        monkeypatch.setattr(pdf_converter.subprocess, "run",
                            FalschesSoffice(returncode=1, erzeugen=set(), stderr="kaputt"))
        pfade = self._dateien(tmp_path, 2)
        assert convert_docx_files_to_pdf(pfade) == {pfade[0]: False, pfade[1]: False}

    def test_teilweiser_ausfall(self, monkeypatch, tmp_path, soffice_da):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice(erzeugen={1}))
        pfade = self._dateien(tmp_path, 2)
        assert convert_docx_files_to_pdf(pfade) == {pfade[0]: False, pfade[1]: True}

    def test_fehlercode_aber_pdf_da_zaehlt_als_erfolg(self, monkeypatch, tmp_path, soffice_da):
        # Entscheidend ist die Datei, nicht der Rueckgabewert von soffice
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice(returncode=81))
        pfade = self._dateien(tmp_path, 1)
        assert convert_docx_files_to_pdf(pfade) == {pfade[0]: True}

    def test_zeitueberschreitung_raeumt_profil_auf(self, monkeypatch, tmp_path, soffice_da, temp_dirs):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice(
            ausnahme=subprocess.TimeoutExpired(cmd="soffice", timeout=120)))
        eingabe = tmp_path / "eingabe"
        eingabe.mkdir()

        with pytest.raises(subprocess.TimeoutExpired):
            convert_docx_files_to_pdf(self._dateien(eingabe, 1))

        assert temp_dirs and not any(p.exists() for p in temp_dirs)

    def test_soffice_fehlt(self, monkeypatch, tmp_path):
        def fehlt():
            raise FileNotFoundError("LibreOffice (soffice) wurde nicht gefunden.")

        aufruf = FalschesSoffice()
        monkeypatch.setattr(pdf_converter, "_find_soffice", fehlt)
        monkeypatch.setattr(pdf_converter.subprocess, "run", aufruf)

        with pytest.raises(FileNotFoundError):
            convert_docx_files_to_pdf(self._dateien(tmp_path, 1))
        assert aufruf.aufrufe == []

    def test_programm_verschwindet_beim_start(self, monkeypatch, tmp_path, soffice_da, temp_dirs):
        monkeypatch.setattr(pdf_converter.subprocess, "run",
                            FalschesSoffice(ausnahme=FileNotFoundError("soffice")))
        eingabe = tmp_path / "eingabe"
        eingabe.mkdir()
        with pytest.raises(FileNotFoundError):
            convert_docx_files_to_pdf(self._dateien(eingabe, 1))
        assert not any(p.exists() for p in temp_dirs)


# ===== Bytes =====

class TestBytesKonvertieren:
    def test_leer(self, monkeypatch):
        aufruf = FalschesSoffice()
        monkeypatch.setattr(pdf_converter.subprocess, "run", aufruf)
        assert convert_docx_bytes_to_pdf([]) == []
        assert aufruf.aufrufe == []

    def test_reihenfolge_bleibt(self, monkeypatch, soffice_da):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice())
        ergebnis = convert_docx_bytes_to_pdf([("a.docx", b"A"), ("b.xlsx", b"B"), ("c.docx", b"C")])
        assert ergebnis == [b"%PDF-A", b"%PDF-B", b"%PDF-C"]

    def test_gleiche_namen_ueberschreiben_sich_nicht(self, monkeypatch, soffice_da):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice())
        ergebnis = convert_docx_bytes_to_pdf([("Turnier.docx", b"eins"), ("Turnier.docx", b"zwei")])
        assert ergebnis == [b"%PDF-eins", b"%PDF-zwei"]

    def test_endung_bleibt_fuer_den_exportfilter(self, monkeypatch, soffice_da):
        aufruf = FalschesSoffice()
        monkeypatch.setattr(pdf_converter.subprocess, "run", aufruf)
        convert_docx_bytes_to_pdf([("a.docx", b"A"), ("b.xlsx", b"B"), ("ohne_endung", b"C")])
        befehl, _ = aufruf.aufrufe[0]
        assert [Path(p).name for p in befehl[-3:]] == ["0000.docx", "0001.xlsx", "0002.docx"]

    def test_fehlschlag_wird_none(self, monkeypatch, soffice_da):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice(erzeugen={0}))
        assert convert_docx_bytes_to_pdf([("a.docx", b"A"), ("b.docx", b"B")]) == [b"%PDF-A", None]

    def test_totalausfall(self, monkeypatch, soffice_da):
        monkeypatch.setattr(pdf_converter.subprocess, "run",
                            FalschesSoffice(returncode=1, erzeugen=set()))
        assert convert_docx_bytes_to_pdf([("a.docx", b"A")]) == [None]

    def test_arbeitsverzeichnis_verschwindet(self, monkeypatch, soffice_da, temp_dirs):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice())
        convert_docx_bytes_to_pdf([("a.docx", b"A")])
        assert len(temp_dirs) == 2  # Arbeitsverzeichnis + soffice-Profil
        assert not any(p.exists() for p in temp_dirs)

    def test_zeitueberschreitung_raeumt_alles_auf(self, monkeypatch, soffice_da, temp_dirs):
        monkeypatch.setattr(pdf_converter.subprocess, "run", FalschesSoffice(
            ausnahme=subprocess.TimeoutExpired(cmd="soffice", timeout=120)))
        # Haengendes LibreOffice gilt als gescheiterte Konvertierung (-> 503)
        assert convert_docx_bytes_to_pdf([("a.docx", b"A"), ("b.docx", b"B")]) == [None, None]
        assert not any(p.exists() for p in temp_dirs)

    def test_soffice_fehlt_raeumt_auf(self, monkeypatch, temp_dirs):
        def fehlt():
            raise FileNotFoundError("nicht installiert")

        monkeypatch.setattr(pdf_converter, "_find_soffice", fehlt)
        assert convert_docx_bytes_to_pdf([("a.docx", b"A")]) == [None]
        assert temp_dirs and not any(p.exists() for p in temp_dirs)
