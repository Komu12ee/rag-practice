"""
Structured legal entity extraction for segmented CIC/SIC decisions.

Input is a SegmentedDecision from src/pipeline/legal_segmenter.py.
The extractor always runs a fast regex layer, then optionally uses local Qwen
via the project's Ollama pattern for a compact JSON-only metadata pass.

Install requirements:
    pip install pydantic ollama

Run embedded tests:
    python src/pipeline/legal_extractor.py --test
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from models.extracted_case import ExtractedCase
from pipeline.legal_segmenter import LegalSegmenter, SegmentedDecision

logger = logging.getLogger(__name__)


QWEN_MODEL = os.getenv("QWEN_MODEL", os.getenv("OLLAMA_QWEN_MODEL", "qwen2.5:14b"))

QWEN_PROMPT_TEMPLATE = """You are extracting structured metadata from a CIC/SIC RTI decision.
Return ONLY one valid JSON object. No markdown. No explanation.

Allowed outcome values: APPEAL_ALLOWED, REJECTED, PARTIAL, PENALTY.
Write key_findings as 3 to 5 short bullet-sized strings, not paragraphs.

JSON schema:
{{
  "appellant_name": "string or null",
  "respondent_name": "string or null",
  "rti_request_summary": "1-2 sentence summary or null",
  "key_findings": ["3-5 short findings"],
  "outcome": "APPEAL_ALLOWED | REJECTED | PARTIAL | PENALTY | null"
}}

Decision context:
HEADER:
{header}

PARTIES:
{parties}

COMMISSION_FINDINGS:
{findings}
"""


class LegalExtractor:
    """Extract structured case metadata from segmented CIC/SIC decisions."""

    CASE_RE = re.compile(
        r"\b(?:CIC|SIC)[/_-][A-Z0-9]+(?:[/_-][A-Z0-9]+)*[/_-][AC][/_-]\d{4}[/_-]\d+\b",
        re.IGNORECASE,
    )
    CASE_FALLBACK_RE = re.compile(
        r"(?i)\b(?:File|Appeal|Complaint|Case)\s*No\.?\s*[:\-]?\s*([A-Z0-9/_\-\.]+)"
    )
    DATE_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b")
    SECTION_RE = re.compile(
        r"(?i)\b(?:Section|Sec\.?|S\.|u/s)\s*"
        r"("
        r"6\s*\(\s*3\s*\)|"
        r"7\s*(?:\(\s*1\s*\))?|"
        r"8\s*\(\s*1\s*\)\s*\(\s*[a-j]\s*\)|"
        r"8\s*\(\s*2\s*\)|"
        r"8\s*\(\s*1\s*\)|"
        r"10|11|19\s*(?:\(\s*3\s*\))?|20\s*(?:\(\s*1\s*\))?|24"
        r")(?=\W|$)"
    )
    PENALTY_AMOUNT_RE = re.compile(
        r"(?i)(?:Rs\.?|INR|₹)\s*([\d,]+)"
    )

    def __init__(self, qwen_model: str = QWEN_MODEL):
        self.qwen_model = qwen_model

    def extract(
        self,
        segmented: SegmentedDecision,
        use_llm: bool = True,
        source_file: str = "",
    ) -> ExtractedCase:
        """Extract metadata, never raising on malformed inputs."""
        try:
            regex_data = self._extract_regex(segmented, source_file)
        except Exception as exc:
            logger.exception("Regex extraction failed unexpectedly: %s", exc)
            regex_data = self._minimal_data(segmented, source_file)

        llm_data: dict[str, Any] = {}
        llm_success = False
        if use_llm:
            try:
                llm_data = self._extract_with_qwen(segmented)
                llm_success = bool(llm_data)
            except Exception as exc:
                logger.warning("Qwen extraction failed; using regex-only result: %s", exc)
                llm_data = {}

        merged = self._merge(regex_data, llm_data)
        merged["extraction_confidence"] = self._confidence(merged, llm_success, use_llm)
        return ExtractedCase(**merged)

    def _minimal_data(self, segmented: SegmentedDecision, source_file: str) -> dict[str, Any]:
        text = self._all_text(segmented)
        source = self._detect_source(text)
        return {
            "case_number": "UNKNOWN",
            "source": source,
            "source_file": source_file,
            "sections_invoked": [],
            "penalty_imposed": False,
            "public_interest_discussed": False,
            "extraction_confidence": 0.2,
        }

    def _extract_regex(self, segmented: SegmentedDecision, source_file: str) -> dict[str, Any]:
        header = segmented.HEADER or ""
        parties = segmented.PARTIES or ""
        findings = segmented.COMMISSION_FINDINGS or ""
        request = segmented.RTI_REQUEST or ""
        penalty = segmented.PENALTY or ""
        full_text = self._all_text(segmented)

        case_number = self._extract_case_number(header) or self._extract_case_number(full_text) or "UNKNOWN"
        sections = self._extract_sections(full_text)
        penalty_amount = self._extract_penalty_amount(penalty) or self._extract_penalty_amount(full_text)
        penalty_imposed = bool(
            penalty_amount
            or re.search(r"(?i)\bpenalt(?:y|ies)\b", penalty)
            or re.search(r"(?i)\bshow\s*cause\b", penalty)
            or re.search(r"(?i)\bSection\s*20\b", penalty)
        )

        data: dict[str, Any] = {
            "case_number": case_number,
            "appeal_number": self._extract_appeal_number(header, case_number),
            "decision_date": self._extract_labelled_date(header, ("decision", "dated", "date of decision")) or self._extract_first_date(header),
            "hearing_date": self._extract_labelled_date(header + "\n" + full_text[:2500], ("hearing", "date of hearing")),
            "commissioner_name": self._extract_commissioner(header),
            "appellant_name": self._extract_party_name(parties, "appellant") or self._extract_party_name(parties, "complainant"),
            "respondent_name": self._extract_party_name(parties, "respondent"),
            "department": self._extract_department(parties),
            "ministry": self._extract_ministry(parties),
            "cpio_name": self._extract_party_name(parties, "cpio") or self._extract_party_name(parties, "pio"),
            "faa_name": self._extract_party_name(parties, "faa") or self._extract_party_name(parties, "first appellate authority"),
            "rti_request_summary": self._summarize_request_regex(request),
            "sections_invoked": sections,
            "outcome": self._infer_outcome(full_text, penalty_imposed),
            "penalty_imposed": penalty_imposed,
            "penalty_amount": penalty_amount,
            "key_findings": self._findings_regex(findings),
            "public_interest_discussed": bool(
                (segmented.PUBLIC_INTEREST or "").strip()
                or re.search(r"(?i)\b(public interest|larger public interest|Section\s*8\s*\(\s*2\s*\))\b", full_text)
            ),
            "source": self._detect_source(case_number + "\n" + header),
            "source_file": source_file,
        }
        return data

    def _extract_with_qwen(self, segmented: SegmentedDecision) -> dict[str, Any]:
        prompt = QWEN_PROMPT_TEMPLATE.format(
            header=self._compact(segmented.HEADER, 1200),
            parties=self._compact(segmented.PARTIES, 800),
            findings=self._compact(segmented.COMMISSION_FINDINGS, 4500),
        )

        import ollama as _ollama_client

        response = _ollama_client.chat(
            model=self.qwen_model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={
                "temperature": 0.0,
                "num_predict": 700,
            },
        )
        content = response.get("message", {}).get("content", "")
        parsed = json.loads(self._clean_json(content))
        return self._sanitize_llm_payload(parsed)

    def _sanitize_llm_payload(self, parsed: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "appellant_name",
            "respondent_name",
            "rti_request_summary",
            "key_findings",
            "outcome",
        }
        return {key: parsed.get(key) for key in allowed if key in parsed}

    def _merge(self, regex_data: dict[str, Any], llm_data: dict[str, Any]) -> dict[str, Any]:
        merged = dict(regex_data)

        # LLM is allowed only for these semantic fields.
        for key in ("appellant_name", "respondent_name", "rti_request_summary", "key_findings", "outcome"):
            value = llm_data.get(key)
            if value not in (None, "", []):
                merged[key] = value

        # Regex always wins for structured fields.
        for key in ("case_number", "appeal_number", "decision_date", "hearing_date", "sections_invoked", "penalty_amount"):
            if regex_data.get(key) not in (None, "", []):
                merged[key] = regex_data[key]

        if merged.get("penalty_amount"):
            merged["penalty_imposed"] = True
        if regex_data.get("penalty_imposed"):
            merged["penalty_imposed"] = True
        if regex_data.get("public_interest_discussed"):
            merged["public_interest_discussed"] = True
        return merged

    def _confidence(self, data: dict[str, Any], llm_success: bool, requested_llm: bool) -> float:
        score = 0.25
        if data.get("case_number") and data.get("case_number") != "UNKNOWN":
            score += 0.20
        if data.get("decision_date"):
            score += 0.10
        if data.get("sections_invoked"):
            score += 0.15
        if data.get("appellant_name") or data.get("respondent_name"):
            score += 0.10
        if data.get("rti_request_summary"):
            score += 0.08
        if data.get("key_findings"):
            score += 0.08
        if data.get("outcome"):
            score += 0.04

        if requested_llm and not llm_success:
            score = min(score, 0.59)
        elif llm_success:
            score += 0.08
        return round(max(0.0, min(1.0, score)), 3)

    def _all_text(self, segmented: SegmentedDecision) -> str:
        parts = [
            segmented.HEADER,
            segmented.PARTIES,
            segmented.BACKGROUND,
            segmented.RTI_REQUEST,
            segmented.CPIO_REPLY,
            segmented.FAA_ORDER,
            segmented.GROUNDS_OF_APPEAL,
            segmented.COMMISSION_FINDINGS,
            segmented.SECTION_ANALYSIS,
            segmented.PUBLIC_INTEREST,
            segmented.DIRECTIONS,
            segmented.PENALTY,
        ]
        return "\n\n".join(part for part in parts if part)

    def _extract_case_number(self, text: str) -> Optional[str]:
        match = self.CASE_RE.search(text or "")
        if match:
            return self._normalize_case_number(match.group(0))

        fallback = self.CASE_FALLBACK_RE.search(text or "")
        if fallback:
            candidate = fallback.group(1).strip(" .,:;")
            if "/" in candidate or "_" in candidate:
                return self._normalize_case_number(candidate)
        return None

    @staticmethod
    def _normalize_case_number(value: str) -> str:
        value = value.strip().replace("\\", "/")
        value = re.sub(r"[_-]+", "/", value)
        value = re.sub(r"/+", "/", value)
        return value.upper().strip("/")

    def _extract_appeal_number(self, header: str, case_number: str) -> Optional[str]:
        if case_number and case_number != "UNKNOWN":
            return case_number
        match = re.search(r"(?i)\b(?:Appeal|Second Appeal)\s*No\.?\s*[:\-]?\s*([A-Z0-9/_\-\.]+)", header or "")
        return self._normalize_case_number(match.group(1)) if match else None

    def _extract_first_date(self, text: str) -> Optional[str]:
        match = self.DATE_RE.search(text or "")
        return self._to_iso_date(match.group(0)) if match else None

    def _extract_labelled_date(self, text: str, labels: tuple[str, ...]) -> Optional[str]:
        for label in labels:
            pattern = rf"(?i)\b{re.escape(label)}\b\s*(?:of\s+\w+\s*)?[:\-]?\s*({self.DATE_RE.pattern})"
            match = re.search(pattern, text or "")
            if match:
                return self._to_iso_date(match.group(1))
        return None

    @staticmethod
    def _to_iso_date(value: str) -> Optional[str]:
        value = value.strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    def _extract_sections(self, text: str) -> list[str]:
        sections: list[str] = []
        seen: set[str] = set()
        for match in self.SECTION_RE.finditer(text or ""):
            section = re.sub(r"\s+", "", match.group(1))
            section = section.lower().replace("(a)", "(a)")
            section = section.upper() if section.isdigit() else section
            section = section.replace("(A)", "(a)").replace("(B)", "(b)").replace("(C)", "(c)").replace("(D)", "(d)")
            section = section.replace("(E)", "(e)").replace("(F)", "(f)").replace("(G)", "(g)").replace("(H)", "(h)")
            section = section.replace("(I)", "(i)").replace("(J)", "(j)")
            key = section.lower()
            if key not in seen:
                sections.append(section)
                seen.add(key)
        return sections

    def _extract_penalty_amount(self, text: str) -> Optional[int]:
        match = self.PENALTY_AMOUNT_RE.search(text or "")
        if not match:
            return None
        digits = re.sub(r"[^\d]", "", match.group(1))
        return int(digits) if digits else None

    @staticmethod
    def _extract_commissioner(header: str) -> Optional[str]:
        patterns = [
            r"(?i)(?:Information Commissioner|Chief Information Commissioner)\s*[:\-]?\s*([^\n]+)",
            r"(?i)\b(?:Shri|Smt\.?|Ms\.?|Mr\.?|Dr\.?)\s+[A-Z][A-Za-z .]+,\s*(?:Information Commissioner|Chief Information Commissioner)",
        ]
        for pattern in patterns:
            match = re.search(pattern, header or "")
            if match:
                return match.group(1 if match.lastindex else 0).strip(" ,")
        return None

    @staticmethod
    def _extract_party_name(parties: str, label: str) -> Optional[str]:
        if not parties:
            return None
        label_pattern = re.escape(label)
        patterns = [
            rf"(?im)^\s*{label_pattern}\s*[:\-]\s*(.+)$",
            rf"(?im)^(.+?)\s+\.{{0,}}\s*{label_pattern}\b.*$",
            rf"(?im)^(.+?)\s+{label_pattern}\b.*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, parties)
            if match:
                name = match.group(1).strip(" .,:;-")
                if name and len(name) <= 180:
                    return name
        return None

    @staticmethod
    def _extract_department(parties: str) -> Optional[str]:
        match = re.search(r"(?i)\b(?:Department|Dept\.?)\s+of\s+([A-Za-z &,/.-]+)", parties or "")
        if match:
            return "Department of " + match.group(1).strip(" ,.")
        match = re.search(r"(?i)\b([A-Za-z &]+Department)\b", parties or "")
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_ministry(parties: str) -> Optional[str]:
        match = re.search(r"(?i)\b(Ministry\s+of\s+[A-Za-z &,/.-]+)", parties or "")
        return match.group(1).strip(" ,.") if match else None

    @staticmethod
    def _summarize_request_regex(request: str) -> Optional[str]:
        text = re.sub(r"\s+", " ", request or "").strip()
        if not text:
            return None
        words = text.split()
        return " ".join(words[:55]).rstrip(" ,;") + ("." if words else "")

    @staticmethod
    def _findings_regex(findings: str) -> list[str]:
        text = re.sub(r"\s+", " ", findings or "").strip()
        if not text:
            return []

        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        selected: list[str] = []
        priority_re = re.compile(r"(?i)\b(commission|observes|finds|directs|section|disclosure|denial|cpio|public interest|penalty)\b")
        for sentence in sentences:
            sentence = sentence.strip(" -.")
            if len(sentence.split()) < 5:
                continue
            if priority_re.search(sentence) or len(selected) < 2:
                selected.append(sentence)
            if len(selected) >= 5:
                break
        return selected[:5]

    @staticmethod
    def _infer_outcome(text: str, penalty_imposed: bool) -> Optional[str]:
        lower = (text or "").lower()
        if penalty_imposed and re.search(r"\b(penalty|show cause|section 20)\b", lower):
            return "PENALTY"
        if re.search(r"\b(partly allowed|partially allowed|redact|severance|section 10)\b", lower):
            return "PARTIAL"
        if re.search(
            r"\b("
            r"appeal\s+is\s+dismissed|"
            r"complaint\s+is\s+dismissed|"
            r"case\s+is\s+dismissed|"
            r"matter\s+is\s+dismissed|"
            r"interference\s+of\s+the\s+commission\s+is\s+not\s+called\s+for|"
            r"no\s+interference\s+is\s+called\s+for|"
            r"reply\s+(?:provided|furnished)\s+is\s+just\s+and\s+proper|"
            r"rejected|"
            r"denied"
            r")\b",
            lower,
        ):
            return "REJECTED"
        if re.search(r"\b(appeal\s+is\s+allowed|appeal.*?allowed|directed\s+to\s+provide|cpio\s+is\s+directed\s+to\s+provide)\b", lower):
            return "APPEAL_ALLOWED"
        return None

    @staticmethod
    def _detect_source(text: str) -> str:
        upper = (text or "").upper()
        if "SIC/" in upper or "STATE INFORMATION COMMISSION" in upper:
            return "SIC"
        return "CIC"

    @staticmethod
    def _compact(text: str, max_chars: int) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rsplit(" ", 1)[0] + "..."

    @staticmethod
    def _clean_json(raw: str) -> str:
        raw = raw or ""
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end + 1]
        raw = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"```\s*$", "", raw.strip())
        raw = re.sub(r",\s*([\]}])", r"\1", raw)
        return raw.strip()


class TestLegalExtractor(unittest.TestCase):
    def _sample_segmented(self) -> SegmentedDecision:
        text = """
CENTRAL INFORMATION COMMISSION
File No: CIC/MFINB/A/2024/001234
Date of Decision: 05/04/2025
Information Commissioner: Shri Example Kumar

Appellant: Ramesh Kumar
Respondent: CPIO, Ministry of Finance, Department of Revenue
First Appellate Authority: Joint Secretary

RTI Request:
The appellant sought file notings and inspection reports regarding tax refund processing delays.

Commission's Findings:
The Commission observes that the CPIO wrongly denied all records under Section 8(1)(j).
Section 8(1)(j) protects personal information but public project records can be disclosed after redaction.
There is larger public interest in disclosure of delay-related administrative records.
The CPIO is directed to provide revised information within 15 days after redacting personal identifiers under Section 10.

Penalty:
Show cause notice under Section 20(1) is issued. Penalty of Rs. 25,000 may be imposed.
"""
        return LegalSegmenter().segment(text)

    def test_regex_extraction_sample(self):
        case = LegalExtractor().extract(self._sample_segmented(), use_llm=False, source_file="sample.pdf")

        self.assertEqual(case.case_number, "CIC/MFINB/A/2024/001234")
        self.assertEqual(case.decision_date, "2025-04-05")
        self.assertEqual(case.source, "CIC")
        self.assertIn("8(1)(j)", case.sections_invoked)
        self.assertIn("10", case.sections_invoked)
        self.assertIn("20(1)", case.sections_invoked)
        self.assertTrue(case.penalty_imposed)
        self.assertEqual(case.penalty_amount, 25000)
        self.assertTrue(case.public_interest_discussed)
        self.assertEqual(case.source_file, "sample.pdf")
        self.assertGreaterEqual(case.extraction_confidence, 0.8)
        self.assertLessEqual(case.extraction_confidence, 1.0)

    def test_malformed_input_does_not_crash(self):
        segmented = SegmentedDecision(COMMISSION_FINDINGS="unstructured text")
        case = LegalExtractor().extract(segmented, use_llm=False)
        self.assertEqual(case.case_number, "UNKNOWN")
        self.assertEqual(case.source, "CIC")
        self.assertEqual(case.sections_invoked, [])

    def test_dates_are_not_extracted_as_sections(self):
        segmented = SegmentedDecision(
            HEADER="File No: CIC/AAOIN/A/2017/102333",
            RTI_REQUEST=(
                "RTI dated 10.03.2016. CPIO reply dated 20.04.2016. "
                "Names of committee members and mobile numbers were sought."
            ),
            COMMISSION_FINDINGS=(
                "The reply furnished to the appellant is just and proper. "
                "Interference of the Commission is not called for."
            ),
        )
        case = LegalExtractor().extract(segmented, use_llm=False)
        self.assertEqual(case.sections_invoked, [])
        self.assertEqual(case.outcome, "REJECTED")


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestLegalExtractor)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract structured metadata from segmented RTI decisions.")
    parser.add_argument("--test", action="store_true", help="Run embedded unit tests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.test:
        return _run_tests()
    print("No action requested. Use --test to run embedded tests.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
