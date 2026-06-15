"""
Rule-based legal section segmenter for CIC/SIC decision text.

The segmenter is designed for batch processing of clean text produced by
src/pipeline/batch_extractor.py. It does not call Qwen or any remote model.

Install requirements:
    pip install pydantic

Run the embedded unit test:
    python src/pipeline/legal_segmenter.py --test
"""

from __future__ import annotations

import argparse
import re
import sys
import unittest
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator


SECTION_KEYS = (
    "HEADER",
    "CASE_HEADER",
    "DATES_TABLE",
    "PARTIES",
    "BACKGROUND",
    "FACTS",
    "RTI_REQUEST",
    "INFORMATION_REQUESTED",
    "CPIO_REPLY",
    "FAA_ORDER",
    "GROUNDS_OF_APPEAL",
    "GROUNDS_FOR_APPEAL",
    "HEARING_SUBMISSIONS",
    "COMMISSION_FINDINGS",
    "COMMISSION_OBSERVATIONS",
    "SECTION_ANALYSIS",
    "PUBLIC_INTEREST",
    "DIRECTIONS",
    "FINAL_ORDER",
    "PENALTY",
)


class SegmentedDecision(BaseModel):
    """Validated segmentation output.

    Each section value is a string. Missing sections are represented by an
    empty string. The confidence map has the same keys as the section fields,
    with values from 0.0 to 1.0.
    """

    HEADER: str = ""
    CASE_HEADER: str = ""
    DATES_TABLE: str = ""
    PARTIES: str = ""
    BACKGROUND: str = ""
    FACTS: str = ""
    RTI_REQUEST: str = ""
    INFORMATION_REQUESTED: str = ""
    CPIO_REPLY: str = ""
    FAA_ORDER: str = ""
    GROUNDS_OF_APPEAL: str = ""
    GROUNDS_FOR_APPEAL: str = ""
    HEARING_SUBMISSIONS: str = ""
    COMMISSION_FINDINGS: str = ""
    COMMISSION_OBSERVATIONS: str = ""
    SECTION_ANALYSIS: str = ""
    PUBLIC_INTEREST: str = ""
    DIRECTIONS: str = ""
    FINAL_ORDER: str = ""
    PENALTY: str = ""
    confidence: dict[str, float] = Field(
        default_factory=lambda: {key: 0.0 for key in SECTION_KEYS}
    )

    @field_validator(*SECTION_KEYS, mode="before")
    @classmethod
    def _coerce_none_to_empty_string(cls, value):
        return "" if value is None else str(value)

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, value: dict[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key in SECTION_KEYS:
            raw = value.get(key, 0.0)
            try:
                score = float(raw)
            except (TypeError, ValueError):
                score = 0.0
            normalized[key] = max(0.0, min(1.0, score))
        return normalized

    def as_section_dict(self) -> dict[str, str]:
        """Return only the requested Dict[str, str] section payload."""
        return {key: getattr(self, key) for key in SECTION_KEYS}


@dataclass(frozen=True)
class BoundaryMatch:
    """One detected section boundary."""

    section: str
    start: int
    end: int
    confidence: float
    marker: str


class LegalSegmenter:
    """Segment CIC/SIC legal decisions into labelled sections.

    Strategy:
    1. Normalize OCR whitespace.
    2. Identify labelled section boundaries with regex patterns.
    3. Slice text between sorted boundaries.
    4. Add heuristic header and party extraction.
    5. Fallback to COMMISSION_FINDINGS when segmentation fails.
    """

    # Ordered by priority: more specific markers should appear before broad ones.
    BOUNDARY_PATTERNS: ClassVar[dict[str, list[tuple[str, float]]]] = {
        "BACKGROUND": [
            (r"\b(?:Background|Brief Facts|Facts|Facts of the Case|Relevant Facts|Case History)\s*[:\-]?", 0.88),
            (r"\bThe facts of the case.*?(?:are|is)\s+(?:as\s+)?(?:under|follows)\s*[:\-]?", 0.78),
        ],
        "FACTS": [
            (r"(?m)^\s*(?:Facts|Facts of the Case|Brief Facts|Relevant Facts)\s*[:\-]?\s*$", 0.90),
        ],
        "INFORMATION_REQUESTED": [
            (r"(?m)^\s*(?:Information Sought|Information Requested|Details Sought|Queries Raised)\s*[:\-]?\s*$", 0.92),
        ],
        "RTI_REQUEST": [
            (r"\b(?:RTI Application|RTI Request|Information Sought|Information Requested|Query Raised|Queries Raised|The appellant sought|The complainant sought)\s*[:\-]?", 0.92),
            (r"\b(?:The Appellant|The applicant|The Complainant)\s+(?:filed|submitted).{0,120}?\bRTI\b.{0,120}?\b(?:seeking|sought)\b\s*[:\-]?", 0.78),
        ],
        "CPIO_REPLY": [
            (r"\b(?:CPIO'?s Reply|Reply of CPIO|CPIO Reply|Response of CPIO|The CPIO replied|The CPIO responded|The CPIO furnished|PIO Reply)\s*[:\-]?", 0.92),
            (r"\b(?:The respondent|The CPIO).{0,80}?\b(?:vide|by)\s+(?:letter|reply).{0,120}?\b(?:stated|informed|replied)\b\s*[:\-]?", 0.76),
        ],
        "FAA_ORDER": [
            (r"\b(?:FAA Order|First Appellate Authority'?s Order|Order of FAA|First Appeal|First Appellate Authority|FAA)\s*[:\-]?", 0.90),
            (r"\bThe\s+FAA\s+(?:vide|by).{0,120}?\b(?:order|decision)\b\s*[:\-]?", 0.78),
        ],
        "GROUNDS_OF_APPEAL": [
            (r"\b(?:Grounds of Appeal|Second Appeal|Grounds for Second Appeal|Appellant'?s Submission|Appellant'?s Arguments|Submissions of the Appellant|Complainant'?s Submission)\s*[:\-]?", 0.90),
            (r"\b(?:Being dissatisfied|Being aggrieved|Aggrieved by).{0,180}?\b(?:second appeal|complaint)\b", 0.74),
        ],
        "GROUNDS_FOR_APPEAL": [
            (r"(?m)^\s*(?:Grounds for Second Appeal|Grounds for Appeal|Grounds of Appeal)\s*[:\-]?\s*$", 0.92),
        ],
        "HEARING_SUBMISSIONS": [
            (r"(?m)^\s*(?:Hearing|Hearing Submissions|Submissions|Proceedings During Hearing)\s*[:\-]?\s*$", 0.88),
            (r"\bDuring\s+the\s+hearing\b", 0.82),
        ],
        "COMMISSION_FINDINGS": [
            (r"(?m)^\s*(?:Decision|Order|Commission'?s Decision|Commission'?s Findings|Observations|Discussion|Analysis and Decision|Findings)\s*[:\-]?\s*$", 0.88),
            (r"\b(?:The Commission observes|The Commission noted|The Commission is of the view|The Commission finds|Upon hearing|After hearing)\b", 0.84),
        ],
        "COMMISSION_OBSERVATIONS": [
            (r"(?m)^\s*(?:Commission'?s Observations|Observations|Commission'?s Findings|Findings)\s*[:\-]?\s*$", 0.90),
            (r"\b(?:The Commission observes|The Commission noted|The Commission finds)\b", 0.84),
        ],
        "SECTION_ANALYSIS": [
            (r"\b(?:Section Analysis|Legal Analysis|Exemption Analysis|Applicability of Section|Analysis of Section)\s*[:\-]?", 0.92),
            (r"\bSection\s+(?:6\(3\)|7|8\(1\)\([a-z]\)|8\(1\)|8\(2\)|10|11|19|20|24)\b.{0,160}?\b(?:RTI Act|Right to Information Act)\b", 0.76),
        ],
        "PUBLIC_INTEREST": [
            (r"\b(?:Public Interest|Larger Public Interest|Public Interest Override|Section 8\(2\))\s*[:\-]?", 0.92),
            (r"\blarger\s+public\s+interest\b", 0.80),
        ],
        "DIRECTIONS": [
            (r"\b(?:Directions?|Final Directions?|Relief|Decision and Directions?|Order and Directions?)\s*[:\-]?", 0.90),
            (r"\b(?:The Commission directs|The respondent is directed|CPIO is directed|PIO is directed|Accordingly,.*?directed)\b", 0.86),
            (r"\b(?:The appeal is disposed of|The complaint is disposed of|Disposed of accordingly)\b", 0.74),
        ],
        "FINAL_ORDER": [
            (r"(?m)^\s*(?:Final Order|Order|Decision|Final Disposal)\s*[:\-]?\s*$", 0.90),
            (r"\b(?:appeal|complaint)\s+is\s+disposed\s+of\b", 0.78),
        ],
        "PENALTY": [
            (r"\b(?:Penalty|Show Cause|Show-Cause|Section 20|Compensation|Disciplinary Action)\s*[:\-]?", 0.92),
            (r"\b(?:show cause notice|penalty proceedings|why penalty should not be imposed)\b", 0.88),
        ],
    }

    HEADER_END_PATTERNS: ClassVar[list[str]] = [
        r"\bAppellant\b",
        r"\bComplainant\b",
        r"\bRespondent\b",
        r"\bCPIO\b",
        r"\bBackground\b",
        r"\bFacts\b",
        r"\bRTI Application\b",
    ]

    PARTY_LINE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?im)^\s*(?:"
        r".*\bAppellant\b.*|"
        r".*\bComplainant\b.*|"
        r".*\bRespondent\b.*|"
        r".*\bCPIO\b.*|"
        r".*\bPIO\b.*|"
        r".*\bFAA\b.*|"
        r".*\bFirst Appellate Authority\b.*"
        r")\s*$"
    )

    CASE_HEADER_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?i)\b(?:CIC|SIC|Appeal\s+No|Complaint\s+No|File\s+No|Case\s+No|Decision\s+No)[\w/\-.: ]+"
    )

    def segment(self, text: str) -> SegmentedDecision:
        """Return validated segmented decision output."""
        normalized = self._normalize_text(text)
        empty_conf = {key: 0.0 for key in SECTION_KEYS}

        if not normalized:
            return SegmentedDecision(confidence=empty_conf)

        boundaries = self._find_boundaries(normalized)
        sections = {key: "" for key in SECTION_KEYS}
        confidence = dict(empty_conf)

        header = self._extract_header(normalized, boundaries)
        if header:
            sections["HEADER"] = header
            sections["CASE_HEADER"] = header
            confidence["HEADER"] = self._header_confidence(header)
            confidence["CASE_HEADER"] = confidence["HEADER"]

        dates_table = self._extract_dates_table(normalized)
        if dates_table:
            sections["DATES_TABLE"] = dates_table
            confidence["DATES_TABLE"] = 0.86

        parties = self._extract_parties(normalized)
        if parties:
            sections["PARTIES"] = parties
            confidence["PARTIES"] = 0.82

        if boundaries:
            self._slice_boundary_sections(normalized, boundaries, sections, confidence)
            self._sync_alias_sections(sections, confidence)

        self._augment_section_analysis(normalized, sections, confidence)
        self._augment_public_interest(normalized, sections, confidence)

        found_core_sections = sum(
            1 for key in ("BACKGROUND", "RTI_REQUEST", "CPIO_REPLY", "COMMISSION_FINDINGS", "DIRECTIONS")
            if sections[key].strip()
        )

        # If the decision has no useful labelled segmentation, preserve the full
        # text as findings so downstream indexing still has searchable content.
        if found_core_sections == 0:
            sections["COMMISSION_FINDINGS"] = normalized
            confidence["COMMISSION_FINDINGS"] = 0.35

        return SegmentedDecision(**sections, confidence=confidence)

    @staticmethod
    def _sync_alias_sections(sections: dict[str, str], confidence: dict[str, float]) -> None:
        aliases = [
            ("BACKGROUND", "FACTS"),
            ("RTI_REQUEST", "INFORMATION_REQUESTED"),
            ("GROUNDS_OF_APPEAL", "GROUNDS_FOR_APPEAL"),
            ("COMMISSION_FINDINGS", "COMMISSION_OBSERVATIONS"),
            ("DIRECTIONS", "FINAL_ORDER"),
        ]
        for old_key, new_key in aliases:
            if not sections.get(new_key) and sections.get(old_key):
                sections[new_key] = sections[old_key]
                confidence[new_key] = confidence.get(old_key, 0.0)
            if not sections.get(old_key) and sections.get(new_key):
                sections[old_key] = sections[new_key]
                confidence[old_key] = confidence.get(new_key, 0.0)

    @staticmethod
    def _extract_dates_table(text: str) -> str:
        rows = []
        pattern = re.compile(
            r"(?im)^\s*(RTI application|CPIO reply|First Appeal|FAA Order|Second Appeal|Complaint|Date of hearing)\s*:?\s*(.+?)\s*$"
        )
        for match in pattern.finditer(text):
            rows.append(f"{match.group(1)}: {' '.join(match.group(2).split())}")
        return "\n".join(rows[:12])

    def _normalize_text(self, text: str) -> str:
        text = "" if text is None else str(text)
        text = text.replace("\x00", " ")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"<!--\s*page\s+\d+\s*-->", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()

    def _find_boundaries(self, text: str) -> list[BoundaryMatch]:
        matches: list[BoundaryMatch] = []
        occupied_spans: list[tuple[int, int]] = []

        for section, patterns in self.BOUNDARY_PATTERNS.items():
            for pattern, score in patterns:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL):
                    start, end = match.span()
                    if self._overlaps_existing(start, end, occupied_spans):
                        continue
                    marker = text[start:end].strip()
                    matches.append(
                        BoundaryMatch(
                            section=section,
                            start=start,
                            end=end,
                            confidence=score,
                            marker=marker,
                        )
                    )
                    occupied_spans.append((start, end))

        matches.sort(key=lambda item: item.start)
        return self._dedupe_nearby_boundaries(matches)

    def _dedupe_nearby_boundaries(self, matches: list[BoundaryMatch]) -> list[BoundaryMatch]:
        deduped: list[BoundaryMatch] = []
        for match in matches:
            if deduped and match.start - deduped[-1].start < 40:
                # Keep the stronger/more specific boundary if two markers fire
                # at almost the same location.
                if match.confidence > deduped[-1].confidence:
                    deduped[-1] = match
                continue
            deduped.append(match)
        return deduped

    @staticmethod
    def _overlaps_existing(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
        return any(start < span_end and end > span_start for span_start, span_end in spans)

    def _slice_boundary_sections(
        self,
        text: str,
        boundaries: list[BoundaryMatch],
        sections: dict[str, str],
        confidence: dict[str, float],
    ) -> None:
        for index, boundary in enumerate(boundaries):
            next_start = boundaries[index + 1].start if index + 1 < len(boundaries) else len(text)
            body_start = boundary.end
            section_text = text[body_start:next_start].strip(" \n:-")
            section_text = self._trim_repeated_heading(section_text, boundary.marker)
            if not section_text:
                continue

            existing = sections[boundary.section].strip()
            if existing:
                sections[boundary.section] = f"{existing}\n\n{section_text}".strip()
                confidence[boundary.section] = max(confidence[boundary.section], boundary.confidence - 0.05)
            else:
                sections[boundary.section] = section_text
                confidence[boundary.section] = boundary.confidence

    @staticmethod
    def _trim_repeated_heading(text: str, marker: str) -> str:
        marker_clean = marker.strip(" :-\n")
        if marker_clean and text.lower().startswith(marker_clean.lower()):
            return text[len(marker_clean):].strip(" :-\n")
        return text

    def _extract_header(self, text: str, boundaries: list[BoundaryMatch]) -> str:
        limit_candidates = [m.start for m in boundaries if m.start > 0]
        for pattern in self.HEADER_END_PATTERNS:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                limit_candidates.append(match.start())

        limit = min(limit_candidates) if limit_candidates else min(len(text), 1800)
        header = text[:limit].strip()

        # If no explicit case header exists, keep only a conservative first page
        # slice so HEADER does not swallow the whole decision.
        if not self.CASE_HEADER_RE.search(header):
            header = "\n".join(header.splitlines()[:20]).strip()

        return header

    def _header_confidence(self, header: str) -> float:
        score = 0.45
        if self.CASE_HEADER_RE.search(header):
            score += 0.30
        if re.search(r"\b(?:Date\s+of\s+Decision|Decision\s+Date|Dated|Date)\b", header, re.I):
            score += 0.15
        if re.search(r"\b(?:Information Commissioner|Commissioner|Chief Information Commissioner)\b", header, re.I):
            score += 0.10
        return min(score, 0.95)

    def _extract_parties(self, text: str) -> str:
        lines = self.PARTY_LINE_RE.findall(text[:5000])
        cleaned: list[str] = []
        seen: set[str] = set()
        for line in lines:
            line = line.strip()
            key = line.lower()
            if line and key not in seen:
                cleaned.append(line)
                seen.add(key)
        return "\n".join(cleaned[:20]).strip()

    def _augment_section_analysis(
        self,
        text: str,
        sections: dict[str, str],
        confidence: dict[str, float],
    ) -> None:
        if sections["SECTION_ANALYSIS"].strip():
            return

        section_mentions = list(
            re.finditer(
                r"(?i)\bSection\s+(?:6\(3\)|7(?:\(1\))?|8\(1\)\([a-z]\)|8\(1\)|8\(2\)|10|11|19(?:\(3\))?|20|24)\b.{0,450}",
                text,
            )
        )
        if not section_mentions:
            return

        snippets = []
        for match in section_mentions[:8]:
            snippets.append(text[match.start():match.end()].strip())

        sections["SECTION_ANALYSIS"] = "\n\n".join(snippets)
        confidence["SECTION_ANALYSIS"] = 0.62

    def _augment_public_interest(
        self,
        text: str,
        sections: dict[str, str],
        confidence: dict[str, float],
    ) -> None:
        if sections["PUBLIC_INTEREST"].strip():
            return

        match = re.search(r"(?is).{0,250}\blarger\s+public\s+interest\b.{0,450}", text)
        if match:
            sections["PUBLIC_INTEREST"] = match.group(0).strip()
            confidence["PUBLIC_INTEREST"] = 0.68


class TestLegalSegmenter(unittest.TestCase):
    """Unit-testable sample covering common CIC decision markers."""

    def test_segments_sample_cic_decision(self):
        sample = """
CENTRAL INFORMATION COMMISSION
File No: CIC/ABCD/A/2024/123456
Date of Decision: 10.05.2025
Information Commissioner: Shri Example Kumar

Appellant: Ramesh Kumar
Respondent: CPIO, Ministry of Example
First Appellate Authority: Joint Secretary

Background:
The appellant filed an RTI application dated 01.01.2025 and thereafter filed
first appeal due to non-receipt of information.

RTI Request:
The appellant sought copies of inspection reports, file notings and action
taken report regarding the public project.

CPIO Reply:
The CPIO replied on 20.01.2025 stating that some records were not traceable
and denied personal details under Section 8(1)(j) of the RTI Act.

FAA Order:
The FAA directed the CPIO to revisit the matter and provide a revised reply.

Grounds of Appeal:
The appellant argued that denial was mechanical and larger public interest
required disclosure.

Commission's Findings:
The Commission observes that the CPIO has not justified why the complete
record is exempt. Section 8(1)(j) protects personal information, but file
notings about public work are disclosable after severing personal identifiers.

Public Interest:
There is larger public interest in disclosure of public project inspection
records.

Directions:
The CPIO is directed to provide revised information within 15 days after
redacting personal identifiers under Section 10.

Penalty:
Show cause notice under Section 20 is not issued at this stage.
"""
        result = LegalSegmenter().segment(sample)
        payload = result.as_section_dict()

        self.assertIn("CIC/ABCD/A/2024/123456", payload["HEADER"])
        self.assertIn("Appellant", payload["PARTIES"])
        self.assertIn("inspection reports", payload["RTI_REQUEST"])
        self.assertIn("Section 8(1)(j)", payload["CPIO_REPLY"])
        self.assertIn("larger public interest", payload["PUBLIC_INTEREST"])
        self.assertIn("directed", payload["DIRECTIONS"].lower())
        self.assertIn("Section 20", payload["PENALTY"])
        self.assertGreaterEqual(result.confidence["RTI_REQUEST"], 0.8)
        self.assertGreaterEqual(result.confidence["COMMISSION_FINDINGS"], 0.8)

    def test_fallback_places_text_in_findings(self):
        sample = "This is an unlabelled decision body with no recognizable headings."
        result = LegalSegmenter().segment(sample)
        self.assertEqual(result.RTI_REQUEST, "")
        self.assertEqual(result.COMMISSION_FINDINGS, sample)
        self.assertEqual(result.confidence["COMMISSION_FINDINGS"], 0.35)


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestLegalSegmenter)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def _demo(text_path: str) -> int:
    text = open(text_path, "r", encoding="utf-8").read()
    result = LegalSegmenter().segment(text)
    print(result.model_dump_json(indent=2, ensure_ascii=False))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Segment CIC/SIC decision text into legal sections.")
    parser.add_argument("--test", action="store_true", help="Run embedded unit tests.")
    parser.add_argument("--text-file", help="Optional .txt file to segment and print as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.test:
        return _run_tests()
    if args.text_file:
        return _demo(args.text_file)

    print("No action requested. Use --test or --text-file path/to/decision.txt", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
