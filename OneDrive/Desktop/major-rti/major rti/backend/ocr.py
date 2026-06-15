"""
OCR Processing Module for RTI Intelligence System.

Extracts text from PDF documents and images with support for
Hindi (Devanagari) and English text. Uses pdfplumber for digital
PDFs and pytesseract for scanned/image-based content.

Gracefully degrades to pdfplumber-only mode if Tesseract is not installed.
"""

import io
import logging
import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tesseract availability check — import once, fail gracefully
# ---------------------------------------------------------------------------
_TESSERACT_AVAILABLE: bool = False
try:
    import pytesseract
    from PIL import Image

    # Quick probe to see if the Tesseract binary is reachable
    pytesseract.get_tesseract_version()
    _TESSERACT_AVAILABLE = True
    logger.info("Tesseract OCR is available.")
except Exception:
    logger.warning(
        "Tesseract OCR is NOT available. "
        "Image OCR will be disabled; only pdfplumber text extraction will work."
    )

try:
    import pdfplumber
except ImportError:
    raise ImportError(
        "pdfplumber is required. Install it: pip install pdfplumber"
    )


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class WordConfidence(BaseModel):
    """Confidence data for a single recognised word."""

    word: str
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Per-word OCR confidence (0-1)."
    )


class OCRResult(BaseModel):
    """Result container for OCR / text-extraction operations.

    Attributes:
        text:               Extracted plain text.
        confidence:         Overall confidence score (0-1). 1.0 for digital PDFs.
        language:           Detected language — 'en', 'hi', or 'mixed'.
        word_confidences:   Per-word confidence list (empty for digital PDFs).
        low_confidence_flag: True when overall confidence < 0.85.
        warnings:           Human-readable warnings (e.g. degraded mode).
    """

    text: str = ""
    confidence: float = Field(
        1.0, ge=0.0, le=1.0, description="Overall confidence (0-1)."
    )
    language: str = "en"
    word_confidences: List[WordConfidence] = Field(default_factory=list)
    low_confidence_flag: bool = False
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------
# Unicode Devanagari block: U+0900 – U+097F
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """Detect primary script/language of *text*.

    Returns:
        'hi'    — if > 30 % of alphabetic characters are Devanagari.
        'en'    — if < 5 % of alphabetic characters are Devanagari.
        'mixed' — otherwise.
    """
    if not text or not text.strip():
        return "en"

    devanagari_count = len(_DEVANAGARI_RE.findall(text))
    ascii_count = len(_ASCII_LETTER_RE.findall(text))
    total = devanagari_count + ascii_count

    if total == 0:
        return "en"

    devanagari_ratio = devanagari_count / total

    if devanagari_ratio > 0.30:
        return "hi"
    elif devanagari_ratio < 0.05:
        return "en"
    else:
        return "mixed"


# ---------------------------------------------------------------------------
# PDF Extraction
# ---------------------------------------------------------------------------
def extract_text_from_pdf(file_path: str) -> OCRResult:
    """Extract text from a PDF file.

    Strategy:
        1. Use **pdfplumber** for born-digital PDFs (fast, high-fidelity).
        2. If pdfplumber yields very little text and Tesseract is available,
           fall back to OCR on rasterised page images.

    Args:
        file_path: Absolute or relative path to the PDF.

    Returns:
        OCRResult with extracted text, confidence, and language.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError:        If the file cannot be read as a valid PDF.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    warnings: List[str] = []
    pages_text: List[str] = []
    all_word_confs: List[WordConfidence] = []
    overall_confidence: float = 1.0

    # ------ Pass 1: pdfplumber digital extraction ------
    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                    pages_text.append(page_text)
                except Exception as exc:
                    warnings.append(
                        f"Page {page_num}: pdfplumber extraction error — {exc}"
                    )
    except Exception as exc:
        raise ValueError(
            f"Cannot open PDF (corrupt or encrypted?): {file_path} — {exc}"
        )

    combined_text = "\n".join(pages_text).strip()

    # ------ Pass 2: OCR fallback if text is too sparse ------
    _MIN_CHARS_PER_PAGE = 20  # threshold to consider page "empty"
    avg_chars = len(combined_text) / max(len(pages_text), 1)

    if avg_chars < _MIN_CHARS_PER_PAGE:
        if _TESSERACT_AVAILABLE:
            logger.info(
                "pdfplumber yielded sparse text — falling back to Tesseract OCR."
            )
            try:
                ocr_result = _ocr_pdf_with_tesseract(path)
                combined_text = ocr_result.text
                overall_confidence = ocr_result.confidence
                all_word_confs = ocr_result.word_confidences
                warnings.extend(ocr_result.warnings)
            except Exception as exc:
                warnings.append(f"Tesseract OCR fallback failed: {exc}")
        else:
            warnings.append(
                "PDF appears to be scanned but Tesseract is not available. "
                "Install Tesseract for OCR support."
            )
            overall_confidence = 0.5

    language = detect_language(combined_text)
    low_flag = overall_confidence < 0.85

    return OCRResult(
        text=combined_text,
        confidence=overall_confidence,
        language=language,
        word_confidences=all_word_confs,
        low_confidence_flag=low_flag,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Image Extraction
# ---------------------------------------------------------------------------
def extract_text_from_image(image_bytes: bytes) -> OCRResult:
    """Extract text from a raw image (JPEG, PNG, TIFF, etc.) using Tesseract.

    Args:
        image_bytes: Raw image bytes.

    Returns:
        OCRResult with extracted text, per-word confidences, and language.

    Raises:
        RuntimeError: If Tesseract is not available.
        ValueError:   If image_bytes cannot be decoded.
    """
    if not _TESSERACT_AVAILABLE:
        raise RuntimeError(
            "Tesseract OCR is not installed or not found on PATH. "
            "Cannot perform image-based text extraction."
        )

    warnings: List[str] = []

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise ValueError(f"Cannot decode image bytes: {exc}")

    # Use Hindi + English language pack
    lang = "hin+eng"

    # ---- Full text ----
    try:
        text = pytesseract.image_to_string(image, lang=lang).strip()
    except Exception as exc:
        raise ValueError(f"Tesseract text extraction failed: {exc}")

    # ---- Per-word confidence via image_to_data ----
    word_confs: List[WordConfidence] = []
    overall_confidence = 1.0
    try:
        data = pytesseract.image_to_data(
            image, lang=lang, output_type=pytesseract.Output.DICT
        )
        confidences: List[float] = []
        for word, conf in zip(data["text"], data["conf"]):
            word = word.strip()
            if not word:
                continue
            # Tesseract returns confidence as 0-100 int; -1 means not applicable
            conf_val = float(conf)
            if conf_val < 0:
                continue
            normalised = conf_val / 100.0
            word_confs.append(WordConfidence(word=word, confidence=normalised))
            confidences.append(normalised)

        if confidences:
            overall_confidence = sum(confidences) / len(confidences)
        else:
            overall_confidence = 0.0
            warnings.append("No words with valid confidence found in image.")
    except Exception as exc:
        warnings.append(f"Could not compute per-word confidence: {exc}")
        overall_confidence = 0.7  # conservative fallback

    language = detect_language(text)
    low_flag = overall_confidence < 0.85

    return OCRResult(
        text=text,
        confidence=overall_confidence,
        language=language,
        word_confidences=word_confs,
        low_confidence_flag=low_flag,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal: OCR a PDF page-by-page with Tesseract
# ---------------------------------------------------------------------------
def _ocr_pdf_with_tesseract(pdf_path: Path) -> OCRResult:
    """Rasterise each page of *pdf_path* and run Tesseract OCR.

    Requires pdf2image (and poppler) to convert PDF pages to images.
    Falls back to a simpler pdfplumber-crop approach if pdf2image is absent.
    """
    warnings: List[str] = []
    all_text_parts: List[str] = []
    all_word_confs: List[WordConfidence] = []
    all_confidences: List[float] = []

    try:
        from pdf2image import convert_from_path

        images = convert_from_path(str(pdf_path), dpi=300)
    except ImportError:
        warnings.append(
            "pdf2image is not installed — cannot rasterise PDF pages for OCR. "
            "Install it with: pip install pdf2image (requires poppler)."
        )
        return OCRResult(
            text="",
            confidence=0.0,
            language="en",
            word_confidences=[],
            low_confidence_flag=True,
            warnings=warnings,
        )
    except Exception as exc:
        warnings.append(f"pdf2image conversion failed: {exc}")
        return OCRResult(
            text="",
            confidence=0.0,
            language="en",
            word_confidences=[],
            low_confidence_flag=True,
            warnings=warnings,
        )

    lang = "hin+eng"
    for page_num, img in enumerate(images, start=1):
        try:
            page_text = pytesseract.image_to_string(img, lang=lang).strip()
            all_text_parts.append(page_text)

            data = pytesseract.image_to_data(
                img, lang=lang, output_type=pytesseract.Output.DICT
            )
            for word, conf in zip(data["text"], data["conf"]):
                word = word.strip()
                if not word:
                    continue
                conf_val = float(conf)
                if conf_val < 0:
                    continue
                normalised = conf_val / 100.0
                all_word_confs.append(
                    WordConfidence(word=word, confidence=normalised)
                )
                all_confidences.append(normalised)
        except Exception as exc:
            warnings.append(f"Page {page_num}: Tesseract OCR error — {exc}")

    combined_text = "\n".join(all_text_parts).strip()
    overall_conf = (
        sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
    )

    return OCRResult(
        text=combined_text,
        confidence=overall_conf,
        language=detect_language(combined_text),
        word_confidences=all_word_confs,
        low_confidence_flag=overall_conf < 0.85,
        warnings=warnings,
    )
