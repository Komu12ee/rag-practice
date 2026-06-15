import os
import sys
from pathlib import Path

# Force UTF-8 encoding on stdout for Windows compatibility with Hindi/Devanagari characters
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add backend to path
_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "backend"))

import fitz
from document_parser import _parse_pdf

def create_test_pdf():
    pdf_path = _ROOT_DIR / "rti-rule-book.pdf"
    test_pdf_path = _ROOT_DIR / "scratch" / "test_single_page.pdf"
    
    if test_pdf_path.exists():
        print(f"Test PDF already exists at {test_pdf_path}")
        return test_pdf_path
        
    print(f"Creating 1-page test PDF from {pdf_path}...")
    src = fitz.open(str(pdf_path))
    doc = fitz.open()
    doc.insert_pdf(src, from_page=0, to_page=0)  # first page
    doc.save(str(test_pdf_path))
    doc.close()
    src.close()
    print(f"Created test PDF at {test_pdf_path}")
    return test_pdf_path

def test_pipeline():
    test_pdf = create_test_pdf()
    
    # Read bytes
    with open(test_pdf, "rb") as f:
        file_bytes = f.read()
        
    print("\n--- Running Document Parser ---")
    result = _parse_pdf(file_bytes, "test_single_page.pdf")
    
    print("\n--- Parser Output ---")
    print(f"Source Type   : {result.source_type}")
    print(f"Page Count    : {result.page_count}")
    print(f"Confidence    : {result.ocr_confidence:.2%}")
    print(f"Language      : {result.language_detected}")
    print(f"Warning       : {result.warning}")
    print(f"Text Length   : {len(result.text)} characters")
    
    print("\n--- Extracted Text Preview ---")
    print(result.text[:1000])
    
if __name__ == "__main__":
    test_pipeline()
