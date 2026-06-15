"""Parse one legal PDF/text file into structured RTI precedent JSON.

Examples:
    python src/pipelines/parse_legal_pdf.py --input data/extracted/cic/CIC_AAOIN_A_2017_102333.txt
    python src/pipelines/parse_legal_pdf.py --input data/cic_pdfs_past_cases/sample.pdf --output C:/tmp/parsed.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pipeline.legal_document_parser import LegalDocumentParser


def read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import fitz  # PyMuPDF
        except Exception as exc:  # pragma: no cover - depends on local optional package
            raise RuntimeError("PDF parsing requires PyMuPDF. Install package 'pymupdf' or pass an extracted .txt file.") from exc
        parts: list[str] = []
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                parts.append(f"<!-- page {page_index} -->")
                parts.append(page.get_text("text"))
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse one CIC/SIC/court PDF or extracted text file.")
    parser.add_argument("--input", required=True, help="PDF or extracted .txt path.")
    parser.add_argument("--output", default="", help="Optional JSON output file. Prints to stdout when omitted.")
    parser.add_argument("--source", default=None, help="Optional source override: CIC, SIC, COURT, CIRCULAR.")
    args = parser.parse_args()

    input_path = Path(args.input)
    text = read_document(input_path)
    parsed = LegalDocumentParser().parse_text(text, source_file=str(input_path), source=args.source)
    payload = parsed.model_dump()

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "output": str(output_path), "case_number": parsed.case_number}, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
