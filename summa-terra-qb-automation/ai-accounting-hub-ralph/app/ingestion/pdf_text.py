"""Deterministic PDF → text extraction via poppler's ``pdftotext`` (CHUNK_7).

We shell out to ``pdftotext -layout`` (already on PATH) rather than depend on a Python PDF
lib, because it is deterministic and preserves column layout well enough for the header and
the summary totals row. Raw text is returned verbatim so the caller can preserve it for audit.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PdfExtractError(RuntimeError):
    """pdftotext is unavailable or failed on the given file."""


def pdftotext_available() -> bool:
    return shutil.which("pdftotext") is not None


def extract_text(pdf_path: Path, *, first: int | None = None, last: int | None = None) -> str:
    """Return layout-preserving text for a page range (1-indexed, inclusive). Whole doc if None.

    Bad-block flate warnings on individual pages are tolerated (real scans have them); we read
    whatever text poppler recovers. Raises PdfExtractError only if no text comes back at all.
    """
    if not pdf_path.is_file():
        raise PdfExtractError(f"PDF not found: {pdf_path}")
    if not pdftotext_available():
        raise PdfExtractError("pdftotext (poppler) is not on PATH")
    cmd = ["pdftotext", "-layout"]
    if first is not None:
        cmd += ["-f", str(first)]
    if last is not None:
        cmd += ["-l", str(last)]
    cmd += [str(pdf_path), "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 and not proc.stdout:
        raise PdfExtractError(f"pdftotext failed: {proc.stderr.strip()[:200]}")
    if not proc.stdout.strip():
        raise PdfExtractError(f"pdftotext returned no text for {pdf_path}")
    return proc.stdout
