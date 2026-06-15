"""
Batch PDF text extraction for MAM-RTI legal corpus indexing.

This utility extracts clean text from archived CIC/SIC decision PDFs and writes
one text file plus one metadata sidecar per source PDF. It is intentionally
standalone so existing backend OCR, upload processing, and frontend behavior
remain unchanged.

Install requirements:
    pip install pymupdf tqdm

Example:
    python src/pipeline/batch_extractor.py --source data/cic_decisions --output data/extracted/cic

Sample metadata output:
    {
      "case_id": "CIC_EDMCD_A_2017_312888",
      "filename": "CIC_EDMCD_A_2017_312888.pdf",
      "path": "data/cic_decisions/CIC_EDMCD_A_2017_312888.pdf",
      "page_count": 8,
      "extraction_date": "2026-06-14T22:34:00+05:30",
      "status": "success",
      "extractor": "pymupdf",
      "text_file": "data/extracted/cic/CIC_EDMCD_A_2017_312888.txt",
      "metadata_file": "data/extracted/cic/CIC_EDMCD_A_2017_312888_meta.json",
      "text_length": 15234,
      "error": null
    }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
    raise SystemExit(
        "Missing dependency: pymupdf. Install with: pip install pymupdf tqdm"
    ) from exc

try:
    from tqdm import tqdm
except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
    raise SystemExit(
        "Missing dependency: tqdm. Install with: pip install pymupdf tqdm"
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ERROR_LOG = PROJECT_ROOT / "data" / "logs" / "extraction_errors.log"


@dataclass
class ExtractionMeta:
    """Metadata written beside each extracted text file."""

    case_id: str
    filename: str
    path: str
    page_count: int
    extraction_date: str
    status: str
    extractor: str
    text_file: str
    metadata_file: str
    text_length: int
    error: str | None = None


def configure_logging(error_log: Path) -> None:
    """Configure failure logging to data/logs/extraction_errors.log."""
    error_log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(error_log, encoding="utf-8"),
        ],
    )


def now_iso() -> str:
    """Return an ISO timestamp for metadata."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_text(text: str) -> str:
    """Normalize whitespace while preserving paragraph/page boundaries."""
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def safe_case_id(pdf_path: Path, source_root: Path) -> str:
    """
    Create a stable filesystem-safe case id.

    The stem is used for normal files. If the same filename appears in multiple
    subfolders, a short hash of its relative path avoids output collisions.
    """
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf_path.stem).strip("._-")
    if not stem:
        stem = "case"

    relative = pdf_path.relative_to(source_root).as_posix()
    parent_marker = pdf_path.parent.relative_to(source_root).as_posix()
    if parent_marker == ".":
        return stem

    digest = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:10]
    return f"{stem}_{digest}"


def iter_pdfs(source_folder: Path) -> Iterable[Path]:
    """Yield PDFs recursively in deterministic order."""
    return sorted(
        path for path in source_folder.rglob("*.pdf")
        if path.is_file()
    )


def extract_with_pymupdf(pdf_path: Path) -> tuple[str, int]:
    """
    Extract text with PyMuPDF.

    This is CPU-only and fast for born-digital CIC/SIC decisions. Scanned PDFs
    may return sparse text; those are still recorded as successful extraction
    unless PyMuPDF cannot open/read the file.
    """
    pages: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        page_count = len(doc)
        for page_number, page in enumerate(doc, start=1):
            page_text = page.get_text("text") or ""
            page_text = clean_text(page_text)
            if page_text:
                pages.append(f"<!-- page {page_number} -->\n{page_text}")
            else:
                pages.append(f"<!-- page {page_number} -->")

    return clean_text("\n\n".join(pages)), page_count


def write_text_atomic(path: Path, text: str) -> None:
    """Write text atomically to avoid partial files on interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def write_json_atomic(path: Path, payload: dict) -> None:
    """Write JSON atomically to avoid corrupt metadata sidecars."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def process_pdf(pdf_path: Path, source_root: Path, output_folder: Path) -> str:
    """
    Process one PDF and return status: success, skipped, or failed.

    A PDF is considered already processed only when both the text and metadata
    files exist. This prevents silent skips after interrupted runs.
    """
    case_id = safe_case_id(pdf_path, source_root)
    text_path = output_folder / f"{case_id}.txt"
    meta_path = output_folder / f"{case_id}_meta.json"

    if text_path.exists() and meta_path.exists():
        return "skipped"

    try:
        text, page_count = extract_with_pymupdf(pdf_path)
        meta = ExtractionMeta(
            case_id=case_id,
            filename=pdf_path.name,
            path=str(pdf_path),
            page_count=page_count,
            extraction_date=now_iso(),
            status="success",
            extractor="pymupdf",
            text_file=str(text_path),
            metadata_file=str(meta_path),
            text_length=len(text),
            error=None,
        )
        write_text_atomic(text_path, text)
        write_json_atomic(meta_path, asdict(meta))
        return "success"
    except Exception as exc:
        logging.exception("Failed to extract %s", pdf_path)
        meta = ExtractionMeta(
            case_id=case_id,
            filename=pdf_path.name,
            path=str(pdf_path),
            page_count=0,
            extraction_date=now_iso(),
            status="failed",
            extractor="pymupdf",
            text_file=str(text_path),
            metadata_file=str(meta_path),
            text_length=0,
            error=f"{type(exc).__name__}: {exc}",
        )
        write_json_atomic(meta_path, asdict(meta))
        return "failed"


def batch_extract(source_folder: Path, output_folder: Path) -> dict[str, int]:
    """Extract all PDFs from source_folder into output_folder."""
    source_folder = source_folder.resolve()
    output_folder = output_folder.resolve()

    if not source_folder.exists():
        raise FileNotFoundError(f"Source folder not found: {source_folder}")
    if not source_folder.is_dir():
        raise NotADirectoryError(f"Source path is not a folder: {source_folder}")

    output_folder.mkdir(parents=True, exist_ok=True)
    pdfs = list(iter_pdfs(source_folder))

    counts = {
        "total": len(pdfs),
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }

    for pdf_path in tqdm(pdfs, desc="Extracting PDFs", unit="pdf"):
        status = process_pdf(pdf_path, source_folder, output_folder)
        counts[status] += 1

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch extract text from CIC/SIC decision PDFs for indexing."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source folder containing PDFs, searched recursively.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output folder for .txt and _meta.json files.",
    )
    parser.add_argument(
        "--error-log",
        default=str(DEFAULT_ERROR_LOG),
        help="Failure log path. Default: data/logs/extraction_errors.log",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(Path(args.error_log))

    try:
        counts = batch_extract(Path(args.source), Path(args.output))
    except Exception as exc:
        logging.exception("Batch extraction failed before completion: %s", exc)
        return 1

    logging.info(
        "Batch extraction complete | total=%s success=%s skipped=%s failed=%s",
        counts["total"],
        counts["success"],
        counts["skipped"],
        counts["failed"],
    )

    return 0 if counts["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
