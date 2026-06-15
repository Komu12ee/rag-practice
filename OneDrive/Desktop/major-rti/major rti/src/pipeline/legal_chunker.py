"""
Legal section-aware chunking for CIC/SIC decisions.

This module converts SegmentedDecision + ExtractedCase objects into retrieval
chunks. It does not use generic fixed-size chunking and does not call any LLM.

Install requirements:
    pip install pydantic

Run embedded tests:
    python src/pipeline/legal_chunker.py --test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from models.extracted_case import ExtractedCase
from pipeline.legal_segmenter import LegalSegmenter, SegmentedDecision


MIN_CHUNK_CHARS = 50
MAX_CHUNK_TOKENS = 800
COMMISSION_FINDINGS_OVERLAP_TOKENS = 50
DEFAULT_CHUNKS_ROOT = PROJECT_ROOT / "data" / "chunks"

CHUNK_TYPES = (
    "CASE_HEADER",
    "DATES_TABLE",
    "PARTIES",
    "FACTS",
    "INFORMATION_REQUESTED",
    "RTI_REQUEST",
    "CPIO_REPLY",
    "FAA_ORDER",
    "GROUNDS_FOR_APPEAL",
    "COMMISSION_FINDINGS",
    "COMMISSION_OBSERVATIONS",
    "COMMISSION_OBSERVATION",
    "SECTION_ANALYSIS",
    "PUBLIC_INTEREST",
    "DIRECTIONS",
    "FINAL_ORDER",
    "PENALTY_REASONING",
    "PRECEDENT_SUMMARY",
    "PIO_LEARNING_SIGNAL",
    "ENTITY_CONTEXT",
    "FULL_SUMMARY",
)

SECTION_TO_CHUNK_TYPE = {
    "RTI_REQUEST": "RTI_REQUEST",
    "CPIO_REPLY": "CPIO_REPLY",
    "FAA_ORDER": "FAA_ORDER",
    "GROUNDS_OF_APPEAL": "GROUNDS_FOR_APPEAL",
    "COMMISSION_FINDINGS": "COMMISSION_FINDINGS",
    "SECTION_ANALYSIS": "SECTION_ANALYSIS",
    "PUBLIC_INTEREST": "PUBLIC_INTEREST",
    "DIRECTIONS": "DIRECTIONS",
    "PENALTY": "PENALTY_REASONING",
}


class LegalChunk(BaseModel):
    """One retrieval-ready legal chunk."""

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_number: str
    source: str
    decision_date: Optional[str] = None
    outcome: Optional[str] = None
    department: Optional[str] = None
    commissioner: Optional[str] = None
    chunk_type: str
    text: str
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("chunk_type")
    @classmethod
    def _validate_chunk_type(cls, value: str) -> str:
        if value not in CHUNK_TYPES:
            raise ValueError(f"Unsupported chunk_type: {value}")
        return value

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("LegalChunk.text cannot be empty")
        return text

    @field_validator("token_count")
    @classmethod
    def _validate_token_count(cls, value: int) -> int:
        return max(1, int(value))


class LegalChunker:
    """Create legal-aware retrieval chunks from segmented decision content."""

    def __init__(
        self,
        chunks_root: str | Path = DEFAULT_CHUNKS_ROOT,
        min_chars: int = MIN_CHUNK_CHARS,
        max_tokens: int = MAX_CHUNK_TOKENS,
        findings_overlap_tokens: int = COMMISSION_FINDINGS_OVERLAP_TOKENS,
    ):
        self.chunks_root = Path(chunks_root)
        self.min_chars = min_chars
        self.max_tokens = max_tokens
        self.findings_overlap_tokens = findings_overlap_tokens

    def chunk(
        self,
        segmented: SegmentedDecision,
        case_metadata: ExtractedCase,
        save: bool = True,
    ) -> list[LegalChunk]:
        """Create chunks and optionally persist them as JSONL."""
        chunks: list[LegalChunk] = []

        for section_name, chunk_type in SECTION_TO_CHUNK_TYPE.items():
            section_text = getattr(segmented, section_name, "") or ""
            section_text = self._clean_text(section_text)
            if len(section_text) < self.min_chars:
                continue

            overlap = self.findings_overlap_tokens if chunk_type == "COMMISSION_FINDINGS" else 0
            parts = self.split_long_section(
                section_text,
                max_tokens=self.max_tokens,
                overlap_tokens=overlap,
            )

            for index, part in enumerate(parts, start=1):
                prefixed = self._prefix_text(chunk_type, part)
                chunks.append(
                    self._make_chunk(
                        case_metadata=case_metadata,
                        chunk_type=chunk_type,
                        text=prefixed,
                        metadata={
                            **self._metadata_for(case_metadata, section_name, chunk_type),
                            "section_name": section_name,
                            "part_index": index,
                            "part_count": len(parts),
                        },
                    )
                )

        for chunk_type, text in self._synthetic_chunks(case_metadata):
            if len(text) < self.min_chars:
                continue
            chunks.append(
                self._make_chunk(
                    case_metadata=case_metadata,
                    chunk_type=chunk_type,
                    text=self._prefix_text(chunk_type, text),
                    metadata=self._metadata_for(case_metadata, chunk_type, chunk_type),
                )
            )

        summary_text = self._build_full_summary(case_metadata)
        if summary_text:
            chunks.append(
                self._make_chunk(
                    case_metadata=case_metadata,
                    chunk_type="FULL_SUMMARY",
                    text=self._prefix_text("FULL_SUMMARY", summary_text),
                    metadata={
                        **self._metadata_for(case_metadata, "FULL_SUMMARY", "FULL_SUMMARY"),
                        "sections_invoked": case_metadata.sections_invoked,
                        "source_file": case_metadata.source_file,
                        "summary_source": "ExtractedCase.outcome + key_findings",
                    },
                )
            )

        if save:
            self.save_jsonl(chunks, case_metadata)

        return chunks

    def split_long_section(
        self,
        text: str,
        max_tokens: int = MAX_CHUNK_TOKENS,
        overlap_tokens: int = 0,
    ) -> list[str]:
        """
        Split only if a legal section exceeds max_tokens.

        Preferred split points are sentence boundaries. If a single sentence is
        too large, it is split by word count. Overlap is applied only between
        long-section subchunks, primarily for COMMISSION_FINDINGS.
        """
        text = self._clean_text(text)
        if not text:
            return []
        if self._approx_tokens(text) <= max_tokens:
            return [text]

        sentences = self._sentences(text)
        chunks: list[list[str]] = []
        current: list[str] = []

        for sentence in sentences:
            sentence_tokens = self._approx_tokens(sentence)

            if sentence_tokens > max_tokens:
                if current:
                    chunks.append(current)
                    current = []
                for word_part in self._split_oversized_sentence(sentence, max_tokens):
                    chunks.append([word_part])
                continue

            candidate = " ".join(current + [sentence])
            if current and self._approx_tokens(candidate) > max_tokens:
                chunks.append(current)
                current = self._overlap_sentences(current, overlap_tokens)
            current.append(sentence)

        if current:
            chunks.append(current)

        return [" ".join(part).strip() for part in chunks if " ".join(part).strip()]

    def save_jsonl(self, chunks: list[LegalChunk], case_metadata: ExtractedCase) -> str:
        """Persist chunks to data/chunks/{source}/{case_number}.jsonl."""
        if not chunks:
            return ""

        path = self._jsonl_path(case_metadata)
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            for chunk in chunks:
                tmp.write(json.dumps(chunk.model_dump(), ensure_ascii=False))
                tmp.write("\n")
            tmp_path = Path(tmp.name)

        tmp_path.replace(path)
        return str(path)

    def _make_chunk(
        self,
        case_metadata: ExtractedCase,
        chunk_type: str,
        text: str,
        metadata: dict[str, Any],
    ) -> LegalChunk:
        return LegalChunk(
            case_number=case_metadata.case_number,
            source=case_metadata.source,
            decision_date=case_metadata.decision_date,
            outcome=case_metadata.outcome,
            department=case_metadata.department,
            commissioner=case_metadata.commissioner_name,
            chunk_type=chunk_type,
            text=text,
            token_count=self._approx_tokens(text),
            metadata=metadata,
        )

    def _metadata_for(self, case_metadata: ExtractedCase, section_name: str, chunk_type: str) -> dict[str, Any]:
        return {
            "case_number": case_metadata.case_number,
            "source_type": case_metadata.source,
            "section_name": section_name,
            "chunk_type": chunk_type,
            "outcome": case_metadata.outcome,
            "public_authority": case_metadata.public_authority,
            "hearing_date": case_metadata.hearing_date,
            "commissioner": case_metadata.commissioner_name,
            "date": case_metadata.decision_date or case_metadata.hearing_date or case_metadata.rti_application_date,
            "rti_sections": case_metadata.rti_sections or case_metadata.sections_invoked,
            "exemption_sections": case_metadata.exemption_sections,
            "sections_invoked": case_metadata.sections_invoked,
            "reasoning_pattern": case_metadata.reasoning_pattern,
            "pio_learning_signal": case_metadata.pio_learning_signal,
            "entities_person": case_metadata.entities_person,
            "entities_authority": case_metadata.entities_authority,
            "entities_department": case_metadata.entities_department,
            "entities_location": case_metadata.entities_location,
            "keywords": self._keywords(case_metadata, chunk_type),
            "source_file": case_metadata.source_file,
        }

    def _synthetic_chunks(self, case_metadata: ExtractedCase) -> list[tuple[str, str]]:
        chunks: list[tuple[str, str]] = []
        header = self._case_header_text(case_metadata)
        if header:
            chunks.append(("CASE_HEADER", header))
        dates = self._dates_table_text(case_metadata)
        if dates:
            chunks.append(("DATES_TABLE", dates))
        parties = self._parties_text(case_metadata)
        if parties:
            chunks.append(("PARTIES", parties))
        if case_metadata.facts:
            chunks.append(("FACTS", case_metadata.facts))
        if case_metadata.information_requested:
            chunks.append(("INFORMATION_REQUESTED", "; ".join(case_metadata.information_requested)))
        if case_metadata.grounds_for_appeal:
            chunks.append(("GROUNDS_FOR_APPEAL", case_metadata.grounds_for_appeal))
        if case_metadata.commission_observations:
            chunks.append(("COMMISSION_OBSERVATION", "; ".join(case_metadata.commission_observations)))
        if case_metadata.final_order:
            chunks.append(("FINAL_ORDER", case_metadata.final_order))
        if case_metadata.precedent_chunk:
            chunks.append(("PRECEDENT_SUMMARY", case_metadata.precedent_chunk))
        if case_metadata.pio_learning_signal:
            chunks.append(("PIO_LEARNING_SIGNAL", case_metadata.pio_learning_signal))
        entity_context = self._entity_context_text(case_metadata)
        if entity_context:
            chunks.append(("ENTITY_CONTEXT", entity_context))
        return chunks

    @staticmethod
    def _case_header_text(case_metadata: ExtractedCase) -> str:
        parts = [
            f"Case number: {case_metadata.case_number}",
            f"Commission: {case_metadata.commission}" if case_metadata.commission else "",
            f"Source: {case_metadata.source}",
            f"Commissioner: {case_metadata.commissioner_name}" if case_metadata.commissioner_name else "",
            f"Outcome: {case_metadata.outcome}" if case_metadata.outcome else "",
        ]
        return ". ".join(part for part in parts if part)

    @staticmethod
    def _dates_table_text(case_metadata: ExtractedCase) -> str:
        fields = [
            ("RTI application date", case_metadata.rti_application_date),
            ("CPIO reply date", case_metadata.cpio_reply_date),
            ("First appeal date", case_metadata.first_appeal_date),
            ("FAA order date", case_metadata.faa_order_date),
            ("Second appeal date", case_metadata.second_appeal_date),
            ("Hearing date", case_metadata.hearing_date),
            ("Decision date", case_metadata.decision_date),
        ]
        return ". ".join(f"{label}: {value}" for label, value in fields if value)

    @staticmethod
    def _parties_text(case_metadata: ExtractedCase) -> str:
        fields = [
            ("Appellant", case_metadata.appellant_name),
            ("Respondent", case_metadata.respondent_name),
            ("Public authority", case_metadata.public_authority),
            ("CPIO/PIO", case_metadata.cpio_name),
            ("FAA", case_metadata.faa_name),
        ]
        return ". ".join(f"{label}: {value}" for label, value in fields if value)

    @staticmethod
    def _entity_context_text(case_metadata: ExtractedCase) -> str:
        fields = [
            ("People", case_metadata.entities_person),
            ("Authorities", case_metadata.entities_authority),
            ("Departments", case_metadata.entities_department),
            ("Locations", case_metadata.entities_location),
            ("Other entities", case_metadata.entities),
        ]
        parts = [f"{label}: {', '.join(values)}" for label, values in fields if values]
        return ". ".join(parts)

    @staticmethod
    def _keywords(case_metadata: ExtractedCase, chunk_type: str) -> list[str]:
        values: list[str] = [chunk_type]
        values.extend(case_metadata.rti_sections or case_metadata.sections_invoked)
        values.extend(case_metadata.exemption_sections)
        values.extend(case_metadata.entities[:8])
        values.extend(case_metadata.reasoning_pattern)
        values.extend(case_metadata.entities_person[:5])
        values.extend(case_metadata.entities_authority[:5])
        values.extend(case_metadata.entities_department[:5])
        values.extend(case_metadata.entities_location[:5])
        for value in (case_metadata.public_authority, case_metadata.outcome):
            if value:
                values.append(value)
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = re.sub(r"\s+", " ", str(value)).strip()
            if text and text.lower() not in seen:
                result.append(text)
                seen.add(text.lower())
        return result[:30]

    def _build_full_summary(self, case_metadata: ExtractedCase) -> str:
        if case_metadata.precedent_chunk:
            return case_metadata.precedent_chunk
        if not case_metadata.outcome or not case_metadata.key_findings:
            return ""

        findings = "; ".join(
            finding.strip(" .")
            for finding in case_metadata.key_findings
            if finding and finding.strip()
        )
        if not findings:
            return ""

        sections = ", ".join(case_metadata.sections_invoked) if case_metadata.sections_invoked else "not specified"
        return (
            f"Case {case_metadata.case_number}. "
            f"Outcome: {case_metadata.outcome}. "
            f"Sections invoked: {sections}. "
            f"Key findings: {findings}."
        )

    def _jsonl_path(self, case_metadata: ExtractedCase) -> Path:
        source = (case_metadata.source or "UNKNOWN").upper()
        case_file = self._safe_filename(case_metadata.case_number) + ".jsonl"
        return self.chunks_root / source / case_file

    @staticmethod
    def _prefix_text(chunk_type: str, text: str) -> str:
        text = text.strip()
        if text.startswith(f"[{chunk_type}]"):
            return text
        return f"[{chunk_type}] {text}"

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("._-") or "UNKNOWN"

    @staticmethod
    def _clean_text(text: str) -> str:
        text = "" if text is None else str(text)
        text = text.replace("\x00", " ")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _approx_tokens(text: str) -> int:
        return max(1, int(round(len(text.split()) * 1.3)))

    @staticmethod
    def _sentences(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", normalized)
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def _split_oversized_sentence(self, sentence: str, max_tokens: int) -> list[str]:
        max_words = max(1, int(max_tokens / 1.3))
        words = sentence.split()
        return [
            " ".join(words[index:index + max_words]).strip()
            for index in range(0, len(words), max_words)
            if words[index:index + max_words]
        ]

    def _overlap_sentences(self, sentences: list[str], overlap_tokens: int) -> list[str]:
        if overlap_tokens <= 0 or not sentences:
            return []

        overlap: list[str] = []
        running_tokens = 0
        for sentence in reversed(sentences):
            sentence_tokens = self._approx_tokens(sentence)
            if overlap and running_tokens + sentence_tokens > overlap_tokens:
                break
            overlap.insert(0, sentence)
            running_tokens += sentence_tokens
            if running_tokens >= overlap_tokens:
                break
        return overlap


class TestLegalChunker(unittest.TestCase):
    def _sample(self) -> tuple[SegmentedDecision, ExtractedCase]:
        segmented = SegmentedDecision(
            RTI_REQUEST="The appellant sought file notings and inspection reports regarding tax refund processing delays.",
            CPIO_REPLY="The CPIO denied personal details under Section 8(1)(j) and gave partial records.",
            FAA_ORDER="The FAA directed the CPIO to revisit the matter and issue a reasoned order.",
            COMMISSION_FINDINGS=(
                "The Commission observes that the CPIO wrongly denied all records under Section 8(1)(j). "
                "Public project records can be disclosed after redaction."
            ),
            PUBLIC_INTEREST="There is larger public interest in disclosure of delay-related administrative records.",
            DIRECTIONS="The CPIO is directed to provide revised information within 15 days.",
            PENALTY="Show cause notice under Section 20(1) is issued to examine whether penalty should be imposed on the CPIO.",
        )
        case = ExtractedCase(
            case_number="CIC/MFINB/A/2024/001234",
            decision_date="2025-04-05",
            hearing_date="2025-03-30",
            commissioner_name="Shri Example Kumar",
            public_authority="Revenue Department",
            department="Department of Revenue",
            sections_invoked=["8(1)(j)", "20(1)"],
            outcome="PENALTY",
            reasoning_pattern=["Wrong blanket denial"],
            pio_learning_signal="Give pointwise reasoned replies.",
            penalty_imposed=True,
            public_interest_discussed=True,
            source="CIC",
            source_file="sample.txt",
            key_findings=[
                "CPIO wrongly denied all records under Section 8(1)(j)",
                "Public project records can be disclosed after redaction",
                "CPIO was directed to provide revised information",
            ],
            extraction_confidence=0.93,
        )
        return segmented, case

    def test_chunk_types_and_prefixes(self):
        segmented, case = self._sample()
        with tempfile.TemporaryDirectory() as tmp:
            chunker = LegalChunker(chunks_root=Path(tmp) / "chunks")
            chunks = chunker.chunk(segmented, case, save=True)

            chunk_types = {chunk.chunk_type for chunk in chunks}
            self.assertIn("RTI_REQUEST", chunk_types)
            self.assertIn("CPIO_REPLY", chunk_types)
            self.assertIn("FAA_ORDER", chunk_types)
            self.assertIn("COMMISSION_FINDINGS", chunk_types)
            self.assertIn("PUBLIC_INTEREST", chunk_types)
            self.assertIn("DIRECTIONS", chunk_types)
            self.assertIn("PENALTY_REASONING", chunk_types)
            self.assertIn("FULL_SUMMARY", chunk_types)

            for chunk in chunks:
                self.assertTrue(chunk.text.startswith(f"[{chunk.chunk_type}]"))
                self.assertGreater(len(chunk.text), 0)
                self.assertGreater(chunk.token_count, 0)
                for field in (
                    "case_number",
                    "public_authority",
                    "outcome",
                    "hearing_date",
                    "reasoning_pattern",
                    "chunk_type",
                    "pio_learning_signal",
                ):
                    self.assertIn(field, chunk.metadata)

            jsonl_path = Path(tmp) / "chunks" / "CIC" / "CIC_MFINB_A_2024_001234.jsonl"
            self.assertTrue(jsonl_path.exists())
            self.assertEqual(len(jsonl_path.read_text(encoding="utf-8").splitlines()), len(chunks))

    def test_long_commission_findings_split(self):
        repeated = "The Commission finds that disclosure is required after redaction. " * 700
        segmented = SegmentedDecision(COMMISSION_FINDINGS=repeated)
        case = ExtractedCase(
            case_number="CIC/TEST/A/2024/000001",
            source="CIC",
            outcome="APPEAL_ALLOWED",
            key_findings=["Disclosure required after redaction"],
            penalty_imposed=False,
            public_interest_discussed=False,
            extraction_confidence=0.8,
        )
        chunks = LegalChunker().chunk(segmented, case, save=False)
        findings_chunks = [chunk for chunk in chunks if chunk.chunk_type == "COMMISSION_FINDINGS"]
        self.assertGreater(len(findings_chunks), 1)
        self.assertTrue(all(chunk.token_count <= MAX_CHUNK_TOKENS + 20 for chunk in findings_chunks))


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestLegalChunker)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create legal-aware chunks from segmented CIC/SIC decisions.")
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
