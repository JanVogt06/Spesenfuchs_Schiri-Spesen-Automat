"""
PDF conversion for generated DOCX and XLSX documents via LibreOffice
headless. LibreOffice picks the export filter by file type, so
TFV forms (DOCX) and NOFV receipts (XLSX) can run in the same call.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.logger import setup_logger

logger = setup_logger("pdf_converter")

# Upper limit for one soffice call. 120s per document would be over an hour and a half for a
# bulk download of 50 matches - a hanging LibreOffice
# must not block any of the few PDF slots for that long.
MAX_CONVERT_SECONDS = 300

# Order: PATH commands first, then known macOS install paths
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


def convert_docx_bytes_to_pdf(documents: List[Tuple[str, bytes]]) -> List[Optional[bytes]]:
    """
    Converts DOCX documents generated in memory to PDF without callers
    having to deal with files.

    LibreOffice only reads and writes files, so the documents run through
    a temporary directory that disappears completely afterwards - nothing
    of the downloads is left on disk.

    All documents are converted in ONE soffice call. The cold start
    dominates the runtime (~2s), the individual file then costs hardly
    anything - one call per document would be many times more expensive.

    Note: the call blocks for seconds. From an async handler
    it belongs in a thread, otherwise the event loop stands still.

    Args:
            documents: List of (file name with .docx or .xlsx extension, bytes)

    Returns:
            List in the same order as the input; None where the
            conversion failed.

            Deliberately a list and not a mapping by file name: two
            matches can produce the same name (tournament assignments have
            no teams), and then one would silently overwrite the other - both
            would get the same PDF.
    """
    if not documents:
        return []

    work_dir = Path(tempfile.mkdtemp(prefix="spesen_pdf_"))

    try:
        paths = []
        for index, (filename, content) in enumerate(documents):
            # Unique name in the working directory, regardless of how
            # the caller names the file later
            path = work_dir / f"{index:04d}{Path(filename).suffix or '.docx'}"
            path.write_bytes(content)
            paths.append(path)

        try:
            convert_docx_files_to_pdf(paths)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as fehler:
            # Hanging or missing LibreOffice: treat like a failed
            # conversion. The download then reports 503 with an
            # understandable message instead of a generic 500.
            logger.error(f"PDF-Konvertierung abgebrochen: {type(fehler).__name__}: {fehler}")
            return [None] * len(paths)

        ergebnis: List[Optional[bytes]] = []
        for path in paths:
            pdf_path = path.with_suffix(".pdf")
            ergebnis.append(pdf_path.read_bytes() if pdf_path.exists() else None)

        return ergebnis
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def convert_docx_files_to_pdf(docx_paths: List[Path]) -> Dict[Path, bool]:
    """
    Converts several DOCX files to PDF in a single LibreOffice call
    (saves the process-start overhead per file). All files must be in the same
    directory, PDFs end up there with the same name (extension .pdf).

    Uses an isolated LibreOffice profile so that conversions running in parallel
    (e.g. several users at once) do not block each other through a profile lock.
    blockieren.

    Returns:
            Dict of DOCX path -> whether the PDF was created successfully.
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
            timeout=min(120 * len(docx_paths), MAX_CONVERT_SECONDS),
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
