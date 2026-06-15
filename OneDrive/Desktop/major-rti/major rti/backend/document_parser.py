import io
import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

import sys
from pathlib import Path

# Add project root, 01_preprocessing, and 02_optimization to path
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))
_PREP_DIR = _ROOT_DIR / "01_preprocessing"
if str(_PREP_DIR) not in sys.path:
    sys.path.insert(0, str(_PREP_DIR))
_OPT_DIR = _ROOT_DIR / "02_optimization"
if str(_OPT_DIR) not in sys.path:
    sys.path.insert(0, str(_OPT_DIR))

# Try to import our custom OCR pipelines
try:
    from stage1_image_prep.pipeline import ImagePrepPipeline
    from stage2_ocr.pipeline import OCRPipeline
    from optimize import optimize
    OCR_PIPELINE_AVAILABLE = True
    logger.info("Custom OCR pre-processing and optimization pipeline loaded successfully.")
except Exception as e:
    OCR_PIPELINE_AVAILABLE = False
    logger.error(f"Could not load custom OCR pipeline: {e}. Falling back to default document parsing.")

# Try to import optional packages
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) is not available. PDF parsing will be limited or unavailable.")

try:
    import pytesseract
    from PIL import Image
    # Quick probe to see if the Tesseract binary is reachable
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except Exception:
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract OCR is not available. Scanned PDF and Image OCR will be disabled.")

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx is not available. DOCX parsing will be unavailable.")


@dataclass
class ParseResult:
    text: str
    source_type: str          # 'pdf' | 'docx' | 'image' | 'text' | 'unknown'
    ocr_confidence: float     # 0.0 to 1.0; 1.0 for native text
    page_count: int
    language_detected: str    # 'en' | 'hi' | 'mixed' | 'unknown'
    raw_file_stored: bool     # True if original stored for audit
    warning: Optional[str]    # Non-None if quality issues found


def parse_uploaded_file(uploaded_file) -> ParseResult:
    """
    Main entry point. Accepts Streamlit UploadedFile object.
    Returns ParseResult with extracted text and metadata.
    CRITICAL: Returns warning if OCR confidence < 0.85.
    """
    ext = uploaded_file.name.lower().split('.')[-1]
    file_bytes = uploaded_file.read()

    # Reset file pointer for downstream usage if needed
    uploaded_file.seek(0)

    if ext == 'pdf':
        return _parse_pdf(file_bytes, uploaded_file.name)
    elif ext in ('docx', 'doc'):
        return _parse_docx(file_bytes, uploaded_file.name)
    elif ext in ('png', 'jpg', 'jpeg', 'tiff', 'bmp'):
        return _parse_image(file_bytes, uploaded_file.name)
    else:
        return ParseResult(
            text='', source_type='unknown', ocr_confidence=0.0,
            page_count=0, language_detected='unknown',
            raw_file_stored=False,
            warning=f'Unsupported file type: {ext}'
        )


def _parse_pdf(file_bytes: bytes, filename: str) -> ParseResult:
    """
    Extract text from PDF. Two-pass strategy:
    Pass 1: Native text extraction (PyMuPDF)
    Pass 2: OCR fallback if native text is sparse (< 50 chars/page)
    """
    # 1. Attempt digital text check first using PyMuPDF if available
    is_digital = False
    native_pages_text = []
    total_pages = 0
    
    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(stream=file_bytes, filetype='pdf')
            total_pages = len(doc)
            
            # Check if every page has a reasonable amount of native text
            digital_pages_count = 0
            for page in doc:
                text = page.get_text().strip()
                native_pages_text.append(text)
                if len(text) > 50:  # Threshold for a page to be considered digital
                    digital_pages_count += 1
            
            # If all pages have digital text, bypass OCR
            if total_pages > 0 and digital_pages_count == total_pages:
                is_digital = True
                
            doc.close()
        except Exception as e:
            logger.warning(f"Error checking if PDF is digital: {e}")
            
    if is_digital:
        print(f"[document_parser.py] PDF {filename} detected as system-generated (digital). Bypassing heavy OCR.")
        full_text = ""
        for page_idx, page_text in enumerate(native_pages_text):
            full_text += f"<!-- page {page_idx + 1} -->\n{page_text}\n\n"
        full_text = full_text.strip()
        lang = _detect_language(full_text)
        return ParseResult(
            text=full_text,
            source_type='pdf',
            ocr_confidence=1.0,
            page_count=total_pages,
            language_detected=lang,
            raw_file_stored=False,
            warning=None
        )

    # 2. Run heavy OCR pipeline if scanned
    if OCR_PIPELINE_AVAILABLE:
        import tempfile
        import shutil
        import uuid

        # Create a temp directory inside scratch to store intermediate files
        scratch_dir = _ROOT_DIR / "scratch"
        scratch_dir.mkdir(exist_ok=True)
        temp_run_id = str(uuid.uuid4())[:8]
        temp_dir = scratch_dir / f"temp_ocr_{temp_run_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            temp_pdf_path = temp_dir / "input.pdf"
            with open(temp_pdf_path, "wb") as f:
                f.write(file_bytes)

            stage1_output_dir = temp_dir / "stage1_output"
            stage2_output_dir = temp_dir / "stage2_output"
            stage1_output_dir.mkdir(parents=True, exist_ok=True)
            stage2_output_dir.mkdir(parents=True, exist_ok=True)

            print(f"[document_parser.py] Starting OCR Stage 1 (Image Prep) for {filename}...")
            # Run Stage 1
            image_prep = ImagePrepPipeline(
                output_dir=stage1_output_dir,
                mask_stamps_in_output=True,
                save_debug_images=False,
            )
            # Stage 1 saves outputs under output_dir / <pdf_stem>
            doc_stem = temp_pdf_path.stem
            image_prep.process(temp_pdf_path)

            print(f"[document_parser.py] Starting OCR Stage 2 (Docling OCR) for {filename}...")
            # Run Stage 2
            ocr_pipeline = OCRPipeline(output_dir=stage2_output_dir)
            ocr_result = ocr_pipeline.process(stage1_output_dir / doc_stem)

            print(f"[document_parser.py] Reading and optimizing OCR output...")
            # Read Stage 2 output structured.md
            structured_md_path = stage2_output_dir / doc_stem / "structured.md"
            if not structured_md_path.exists():
                raise FileNotFoundError(f"OCR failed to produce structured.md at {structured_md_path}")

            raw_markdown = structured_md_path.read_text(encoding="utf-8")

            # Run Stage 3: Optimize Markdown
            optimized_markdown = optimize(raw_markdown)

            # Calculate average OCR confidence score
            conf_scores = [p.confidence for p in ocr_result.pages if p.confidence is not None]
            avg_confidence = sum(conf_scores) / len(conf_scores) if conf_scores else 1.0

            total_pages = ocr_result.total_pages
            lang = _detect_language(optimized_markdown)

            print(f"[document_parser.py] OCR pipeline complete for {filename}. Pages: {total_pages}, Confidence: {avg_confidence:.2%}")

            warning = None
            if avg_confidence < 0.85:
                warning = (
                    f'OCR quality warning: Confidence: {avg_confidence:.0%}. '
                    f'Manual review of extracted text recommended.'
                )

            return ParseResult(
                text=optimized_markdown,
                source_type='pdf',
                ocr_confidence=avg_confidence,
                page_count=total_pages,
                language_detected=lang,
                raw_file_stored=False,
                warning=warning
            )

        except Exception as exc:
            logger.error(f"Error in custom OCR pipeline, falling back to default PDF parser: {exc}")
            print(f"[document_parser.py] ERROR in custom OCR pipeline: {exc}. Falling back to default PDF parser.")
            # Fall back to default PyMuPDF/pytesseract parser
        finally:
            # Clean up temp folder
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not remove temp OCR directory {temp_dir}: {e}")

    # --- FALLBACK / DEFAULT PARSER ---
    if not PYMUPDF_AVAILABLE:
        return ParseResult(
            text='', source_type='pdf', ocr_confidence=0.0,
            page_count=0, language_detected='unknown',
            raw_file_stored=False,
            warning='PyMuPDF (fitz) is not installed. Cannot parse PDF.'
        )

    try:
        doc = fitz.open(stream=file_bytes, filetype='pdf')
    except Exception as e:
        return ParseResult(
            text='', source_type='pdf', ocr_confidence=0.0,
            page_count=0, language_detected='unknown',
            raw_file_stored=False,
            warning=f'Failed to open PDF file: {str(e)}'
        )

    pages = []
    ocr_pages = 0
    native_pages = 0
    total_pages = len(doc)
    
    # Track average OCR confidence across pages where OCR is used
    total_ocr_conf = 0.0

    for page in doc:
        native_text = page.get_text().strip()
        if len(native_text) > 50:  # Native text present
            pages.append(native_text)
            native_pages += 1
        else:  # Scanned page — use OCR
            if TESSERACT_AVAILABLE:
                try:
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
                    ocr_data = pytesseract.image_to_data(
                        img, lang='hin+eng',
                        output_type=pytesseract.Output.DICT
                    )
                    conf_scores = [int(c) for c in ocr_data['conf'] if str(c).isdigit() and int(c) > 0]
                    avg_conf = (sum(conf_scores) / len(conf_scores) / 100.0) if conf_scores else 0.0
                    total_ocr_conf += avg_conf
                    
                    text = pytesseract.image_to_string(img, lang='hin+eng')
                    pages.append(f'[OCR Page {page.number+1}, conf={avg_conf:.0%}]\n{text}')
                    ocr_pages += 1
                except Exception as e:
                    pages.append(f'[OCR Page {page.number+1} Failed: {str(e)}]')
                    ocr_pages += 1
            else:
                pages.append(f'[Page {page.number+1}: Scanned page, OCR unavailable]')
                ocr_pages += 1

    full_text = '\n\n'.join(pages)
    
    # Calculate overall OCR confidence:
    if total_pages == 0:
        ocr_confidence = 1.0
    elif ocr_pages == 0:
        ocr_confidence = 1.0
    else:
        avg_ocr_page_conf = total_ocr_conf / ocr_pages
        ocr_confidence = (native_pages * 1.0 + ocr_pages * avg_ocr_page_conf) / total_pages

    warning = None
    if ocr_pages > 0 and not TESSERACT_AVAILABLE:
        warning = 'PDF appears to be scanned but Tesseract OCR is not available. Text could not be extracted.'
    elif ocr_confidence < 0.85:
        warning = (
            f'OCR quality warning: {ocr_pages} of {total_pages} pages required OCR. '
            f'Confidence: {ocr_confidence:.0%}. Manual review of extracted text recommended.'
        )

    lang = _detect_language(full_text)
    return ParseResult(
        text=full_text, source_type='pdf', ocr_confidence=ocr_confidence,
        page_count=total_pages, language_detected=lang,
        raw_file_stored=False, warning=warning
    )


def _parse_docx(file_bytes: bytes, filename: str) -> ParseResult:
    """Extract text from DOCX/DOC. Native text, no OCR needed."""
    if not DOCX_AVAILABLE:
        return ParseResult(
            text='', source_type='docx', ocr_confidence=0.0,
            page_count=0, language_detected='unknown',
            raw_file_stored=False,
            warning='python-docx is not installed. Cannot parse DOCX.'
        )

    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        full_text = '\n'.join(paragraphs)
        lang = _detect_language(full_text)
        return ParseResult(
            text=full_text, source_type='docx', ocr_confidence=1.0,
            page_count=1, language_detected=lang,
            raw_file_stored=False, warning=None
        )
    except Exception as e:
        return ParseResult(
            text='', source_type='docx', ocr_confidence=0.0,
            page_count=0, language_detected='unknown',
            raw_file_stored=False,
            warning=f'Failed to parse DOCX file: {str(e)}'
        )


def _parse_image(file_bytes: bytes, filename: str) -> ParseResult:
    """OCR on standalone image file."""
    if not TESSERACT_AVAILABLE:
        return ParseResult(
            text='', source_type='image', ocr_confidence=0.0,
            page_count=1, language_detected='unknown',
            raw_file_stored=False,
            warning='Tesseract OCR is not available. Cannot perform OCR on image.'
        )

    try:
        img = Image.open(io.BytesIO(file_bytes))
        ocr_data = pytesseract.image_to_data(
            img, lang='hin+eng', output_type=pytesseract.Output.DICT
        )
        conf_scores = [int(c) for c in ocr_data['conf'] if str(c).isdigit() and int(c) > 0]
        avg_conf = (sum(conf_scores) / len(conf_scores) / 100.0) if conf_scores else 0.0
        text = pytesseract.image_to_string(img, lang='hin+eng')
        
        warning = None
        if avg_conf < 0.85:
            warning = f'Low OCR confidence: {avg_conf:.0%}. Manual verification required.'
            
        lang = _detect_language(text)
        return ParseResult(
            text=text, source_type='image', ocr_confidence=avg_conf,
            page_count=1, language_detected=lang,
            raw_file_stored=False, warning=warning
        )
    except Exception as e:
        return ParseResult(
            text='', source_type='image', ocr_confidence=0.0,
            page_count=1, language_detected='unknown',
            raw_file_stored=False,
            warning=f'Failed to perform OCR on image: {str(e)}'
        )


def _detect_language(text: str) -> str:
    """Simple Devanagari character detection for Hindi vs English."""
    devanagari = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    ascii_alpha = sum(1 for c in text if c.isalpha() and c.isascii())
    total = devanagari + ascii_alpha
    if total == 0:
        return 'unknown'
    ratio = devanagari / total
    if ratio > 0.3:  # Adjusted to match detect_language in ocr.py (>30% devanagari is hi)
        return 'hi'
    elif ratio > 0.05:
        return 'mixed'
    return 'en'
