"""
PDF-Konvertierung fuer generierte DOCX-Dokumente via LibreOffice headless.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from utils.logger import setup_logger

logger = setup_logger("pdf_converter")

# Reihenfolge: zuerst PATH-Kommandos, dann bekannte macOS-Installationspfade
_SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def _find_soffice() -> str:
    for candidate in _SOFFICE_CANDIDATES:
        if Path(candidate).is_absolute():
            if Path(candidate).exists():
                return candidate
        elif shutil.which(candidate):
            return candidate

    raise FileNotFoundError(
        "LibreOffice (soffice) wurde nicht gefunden. "
        "Fuer den PDF-Export muss LibreOffice installiert sein."
    )


def convert_docx_bytes_to_pdf(documents: List[Tuple[str, bytes]]) -> Dict[str, bytes]:
    """
    Konvertiert im Speicher erzeugte DOCX-Dokumente zu PDF, ohne dass Aufrufer
    mit Dateien hantieren muessen.

    LibreOffice liest und schreibt nur Dateien, also laufen die Dokumente durch
    ein temporaeres Verzeichnis, das danach restlos verschwindet - es bleibt
    nichts von den Downloads auf der Platte zurueck.

    Alle Dokumente werden in EINEM soffice-Aufruf konvertiert. Der Kaltstart
    dominiert die Laufzeit (~2s), die einzelne Datei kostet danach kaum noch
    etwas - ein Aufruf pro Dokument waere um ein Vielfaches teurer.

    Achtung: der Aufruf blockiert fuer Sekunden. Aus einem async-Handler
    gehoert er in einen Thread, sonst steht der Event-Loop still.

    Args:
        documents: Liste von (Dateiname mit .docx-Endung, DOCX-Bytes)

    Returns:
        Dict Dateiname -> PDF-Bytes. Dokumente, deren Konvertierung
        fehlschlug, fehlen im Ergebnis.
    """
    if not documents:
        return {}

    work_dir = Path(tempfile.mkdtemp(prefix="spesen_pdf_"))

    try:
        paths = []
        for filename, content in documents:
            path = work_dir / filename
            path.write_bytes(content)
            paths.append(path)

        convert_docx_files_to_pdf(paths)

        results = {}
        for path in paths:
            pdf_path = path.with_suffix(".pdf")
            if pdf_path.exists():
                results[path.name] = pdf_path.read_bytes()

        return results
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def convert_docx_files_to_pdf(docx_paths: List[Path]) -> Dict[Path, bool]:
    """
    Konvertiert mehrere DOCX-Dateien in einem einzigen LibreOffice-Aufruf zu PDF
    (spart den Prozessstart-Overhead pro Datei). Alle Dateien muessen im selben
    Verzeichnis liegen, PDFs landen dort mit gleichem Namen (Endung .pdf).

    Nutzt ein isoliertes LibreOffice-Profil, damit parallel laufende Konvertierungen
    (z.B. mehrere User gleichzeitig) sich nicht gegenseitig durch ein Profil-Lock
    blockieren.

    Returns:
        Dict von DOCX-Pfad -> ob die PDF erfolgreich erstellt wurde.
    """
    docx_paths = [Path(p) for p in docx_paths]
    if not docx_paths:
        return {}

    output_dir = docx_paths[0].parent
    soffice = _find_soffice()
    profile_dir = tempfile.mkdtemp(prefix="soffice_profile_")

    try:
        result = subprocess.run(
            [
                soffice,
                "--headless",
                f"-env:UserInstallation=file://{profile_dir}",
                "--convert-to", "pdf",
                "--outdir", str(output_dir),
                *[str(p) for p in docx_paths],
            ],
            capture_output=True,
            text=True,
            timeout=120 * len(docx_paths),
        )

        if result.returncode != 0:
            logger.error(
                f"soffice-Batch-Konvertierung meldete Fehler (returncode={result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

        results = {}
        for docx_path in docx_paths:
            pdf_path = docx_path.with_suffix(".pdf")
            results[docx_path] = pdf_path.exists()
            if not pdf_path.exists():
                logger.error(f"PDF-Konvertierung fehlgeschlagen fuer {docx_path.name}")
            else:
                logger.info(f"PDF erstellt: {pdf_path}")

        return results
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)
