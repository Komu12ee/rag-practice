"""
Assemble bounded legal precedent context for local Qwen analysis.

This module does not call Qwen. It prepares a deterministic prompt payload that
can be passed to the existing Ollama/Qwen chat integration as a single user
message, matching the call pattern already used elsewhere in the project.

Install requirements:
    pip install pydantic

Run embedded tests:
    python src/retrieval/context_assembler.py --test
"""

from __future__ import annotations

import argparse
import re
import sys
import unittest
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from retrieval.hybrid_retriever import RetrievedChunk


MAX_TOTAL_TOKENS = 6000
SYSTEM_PROMPT_TOKENS = 500
CONTEXT_BLOCK_TOKENS = 4500
QUERY_BLOCK_TOKENS = 500
RESERVE_TOKENS = 500

CHUNK_PRIORITY = {
    "COMMISSION_FINDINGS": 1,
    "SECTION_ANALYSIS": 2,
    "DIRECTIONS": 3,
    "PUBLIC_INTEREST": 4,
    "PENALTY_REASONING": 5,
    "RTI_REQUEST": 6,
    "FULL_SUMMARY": 7,
}

QUERY_TYPES = {
    "pio_assistance",
    "appeal_analysis",
    "exemption_check",
}


class AssembledContext(BaseModel):
    """Prompt package sent downstream to Qwen."""

    system_prompt: str
    context_block: str
    query_block: str
    full_prompt: str
    token_estimate: int = Field(ge=0, le=MAX_TOTAL_TOKENS)
    sources_used: list[str] = Field(default_factory=list)
    chunk_types_used: list[str] = Field(default_factory=list)

    @field_validator("system_prompt", "context_block", "query_block", "full_prompt")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return str(value or "").strip()


class ContextAssembler:
    """Build a Qwen-ready legal context from retrieved precedent chunks."""

    def __init__(
        self,
        max_total_tokens: int = MAX_TOTAL_TOKENS,
        system_tokens: int = SYSTEM_PROMPT_TOKENS,
        context_tokens: int = CONTEXT_BLOCK_TOKENS,
        query_tokens: int = QUERY_BLOCK_TOKENS,
        reserve_tokens: int = RESERVE_TOKENS,
    ):
        self.max_total_tokens = max_total_tokens
        self.system_tokens = system_tokens
        self.context_tokens = context_tokens
        self.query_tokens = query_tokens
        self.reserve_tokens = reserve_tokens

    def assemble(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        query_type: str = "pio_assistance",
    ) -> AssembledContext:
        """Create system, precedent, and query blocks within a 6000-token cap."""
        query_type = self._normalize_query_type(query_type)
        system_prompt = self._truncate_to_tokens(
            self._system_prompt(query_type),
            self.system_tokens,
        )
        query_block = self._build_query_block(query, query_type)
        selected_chunks = self._select_chunks(retrieved_chunks, self.context_tokens)
        context_block = self._build_context_block(selected_chunks)

        full_prompt = self._join_prompt(system_prompt, context_block, query_block)
        token_estimate = self._approx_tokens(full_prompt)

        if token_estimate > self.max_total_tokens:
            context_budget = max(
                0,
                self.max_total_tokens
                - self.reserve_tokens
                - self._approx_tokens(system_prompt)
                - self._approx_tokens(query_block),
            )
            selected_chunks = self._select_chunks(retrieved_chunks, context_budget)
            context_block = self._build_context_block(selected_chunks)
            full_prompt = self._join_prompt(system_prompt, context_block, query_block)
            token_estimate = min(self._approx_tokens(full_prompt), self.max_total_tokens)

        return AssembledContext(
            system_prompt=system_prompt,
            context_block=context_block,
            query_block=query_block,
            full_prompt=full_prompt,
            token_estimate=token_estimate,
            sources_used=self._unique_preserve_order(chunk.case_number for chunk in selected_chunks),
            chunk_types_used=self._unique_preserve_order(chunk.chunk_type for chunk in selected_chunks),
        )

    def _select_chunks(
        self,
        retrieved_chunks: list[RetrievedChunk],
        token_budget: int,
    ) -> list[RetrievedChunk]:
        if token_budget <= 0:
            return []

        selected: list[RetrievedChunk] = []
        used_ids: set[str] = set()
        used_tokens = self._approx_tokens(self._context_header())

        for chunk in self._rank_chunks(retrieved_chunks):
            if chunk.chunk_id in used_ids:
                continue
            if chunk.chunk_type not in CHUNK_PRIORITY:
                continue

            formatted = self._format_chunk(chunk, source_index=len(selected) + 1)
            formatted_tokens = self._approx_tokens(formatted)
            remaining = token_budget - used_tokens

            if remaining <= 0:
                break

            if formatted_tokens > remaining:
                truncated = self._format_chunk(
                    chunk,
                    source_index=len(selected) + 1,
                    text_budget=max(60, remaining - 80),
                )
                if self._approx_tokens(truncated) > remaining:
                    continue
                formatted = truncated

            used_tokens += self._approx_tokens(formatted)
            selected.append(self._copy_with_text(chunk, self._extract_formatted_text(formatted, chunk.text)))
            used_ids.add(chunk.chunk_id)

        return selected

    def _build_context_block(self, chunks: list[RetrievedChunk]) -> str:
        lines = [self._context_header()]
        if not chunks:
            lines.append("No retrieved CIC/SIC/circular precedent chunks were available.")
            return "\n".join(lines).strip()

        for index, chunk in enumerate(chunks, start=1):
            lines.append(self._format_chunk(chunk, source_index=index))
        return "\n\n".join(lines).strip()

    def _build_query_block(self, query: str, query_type: str) -> str:
        clean_query = self._clean_text(query)
        clean_query = self._truncate_to_tokens(clean_query, max(1, self.query_tokens - 60))
        label = {
            "pio_assistance": "PIO assistance request",
            "appeal_analysis": "Appeal analysis request",
            "exemption_check": "Exemption check request",
        }[query_type]
        return (
            "USER RTI QUERY\n"
            f"Query type: {label}\n"
            "Question/document text:\n"
            f"{clean_query}"
        ).strip()

    @staticmethod
    def _system_prompt(query_type: str) -> str:
        base = (
            "You are an expert RTI legal analysis assistant for a Public Information Officer. "
            "Use only the provided legal precedents and the user's RTI query. "
            "Cite case numbers whenever relying on a precedent. "
            "Separate binding statutory requirements from persuasive CIC/SIC precedent. "
            "Do not invent case facts, sections, dates, departments, or outcomes. "
        )
        if query_type == "appeal_analysis":
            task = (
                "Assess appeal strength, relevant exemptions, disclosure duties, procedural lapses, "
                "and likely Commission reasoning. Return concise recommendations with citations."
            )
        elif query_type == "exemption_check":
            task = (
                "Identify applicable RTI exemptions, public interest override issues, severability, "
                "third-party consultation needs, and disclosure-safe alternatives. Return citations."
            )
        else:
            task = (
                "Assist the PIO with disclosure/rejection/transfer options, timelines, legal risks, "
                "and draftable recommendation points. Return citations and practical next steps."
            )
        return base + task

    @staticmethod
    def _context_header() -> str:
        return (
            "LEGAL PRECEDENTS\n"
            "Use these retrieved CIC/SIC/circular chunks as citation-backed context. "
            "Prefer COMMISSION_FINDINGS and SECTION_ANALYSIS over summaries when reasoning."
        )

    def _format_chunk(
        self,
        chunk: RetrievedChunk,
        source_index: int,
        text_budget: Optional[int] = None,
    ) -> str:
        text = self._clean_text(chunk.text)
        if text_budget is not None:
            text = self._truncate_to_tokens(text, text_budget)
        return (
            f"[SOURCE {source_index}]\n"
            f"Case: {chunk.case_number}\n"
            f"Source: {chunk.source or 'N/A'}\n"
            f"Chunk Type: {chunk.chunk_type}\n"
            f"Decision Date: {chunk.decision_date or 'N/A'}\n"
            f"Outcome: {chunk.outcome or 'N/A'}\n"
            f"Department: {chunk.department or 'N/A'}\n"
            f"Retrieval Rank: {chunk.rank}\n"
            f"RRF Score: {chunk.rrf_score:.4f}\n"
            "Text:\n"
            f"{text}"
        ).strip()

    @staticmethod
    def _rank_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return sorted(
            chunks or [],
            key=lambda chunk: (
                CHUNK_PRIORITY.get(chunk.chunk_type, 999),
                chunk.rank,
                -float(chunk.rrf_score or 0.0),
                chunk.case_number,
            ),
        )

    @staticmethod
    def _join_prompt(system_prompt: str, context_block: str, query_block: str) -> str:
        return (
            f"SYSTEM INSTRUCTIONS\n{system_prompt}\n\n"
            f"{context_block}\n\n"
            f"{query_block}\n\n"
            "RESPONSE REQUIREMENTS\n"
            "Return a structured, concise legal analysis with: recommendation, applicable RTI sections, "
            "similar precedents with case numbers, risks, and suggested PIO action."
        ).strip()

    @staticmethod
    def _copy_with_text(chunk: RetrievedChunk, text: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk.chunk_id,
            case_number=chunk.case_number,
            source=chunk.source,
            chunk_type=chunk.chunk_type,
            text=text,
            decision_date=chunk.decision_date,
            outcome=chunk.outcome,
            department=chunk.department,
            bm25_score=chunk.bm25_score,
            vector_score=chunk.vector_score,
            rrf_score=chunk.rrf_score,
            rank=chunk.rank,
        )

    @staticmethod
    def _extract_formatted_text(formatted: str, original_text: str) -> str:
        marker = "Text:\n"
        if marker not in formatted:
            return original_text
        return formatted.split(marker, 1)[1].strip()

    @staticmethod
    def _normalize_query_type(query_type: str) -> str:
        value = str(query_type or "pio_assistance").strip().lower()
        if value not in QUERY_TYPES:
            return "pio_assistance"
        return value

    @staticmethod
    def _clean_text(text: str) -> str:
        text = "" if text is None else str(text)
        text = text.replace("\x00", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _truncate_to_tokens(text: str, token_budget: int) -> str:
        text = ContextAssembler._clean_text(text)
        if token_budget <= 0:
            return ""
        if ContextAssembler._approx_tokens(text) <= token_budget:
            return text
        max_words = max(1, int(token_budget / 1.3))
        words = text.split()
        truncated = " ".join(words[:max_words]).strip()
        if len(words) > max_words:
            truncated = truncated.rstrip(" .,;:") + " ..."
        return truncated

    @staticmethod
    def _approx_tokens(text: str) -> int:
        return max(0, int(round(len(str(text or "").split()) * 1.3)))

    @staticmethod
    def _unique_preserve_order(values) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                output.append(text)
        return output


class TestContextAssembler(unittest.TestCase):
    def _chunk(
        self,
        chunk_id: str,
        case_number: str,
        chunk_type: str,
        text: str,
        rank: int,
        score: float = 0.9,
    ) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk_id,
            case_number=case_number,
            source="CIC",
            chunk_type=chunk_type,
            text=text,
            decision_date="2024-01-01",
            outcome="PARTIAL",
            department="Revenue",
            bm25_score=10.0,
            vector_score=0.9,
            rrf_score=score,
            rank=rank,
        )

    def test_priority_and_prompt_shape(self):
        chunks = [
            self._chunk("summary", "CIC/2", "FULL_SUMMARY", "[FULL_SUMMARY] short summary text " * 5, 1),
            self._chunk(
                "findings",
                "CIC/1",
                "COMMISSION_FINDINGS",
                "[COMMISSION_FINDINGS] The Commission held that file notings may be disclosed after redaction.",
                5,
            ),
            self._chunk(
                "directions",
                "CIC/3",
                "DIRECTIONS",
                "[DIRECTIONS] The CPIO was directed to provide revised information within 15 days.",
                2,
            ),
        ]

        assembled = ContextAssembler().assemble(
            "Can file noting be denied under Section 8(1)(j)?",
            chunks,
            "exemption_check",
        )

        self.assertLessEqual(assembled.token_estimate, MAX_TOTAL_TOKENS)
        self.assertIn("SYSTEM INSTRUCTIONS", assembled.full_prompt)
        self.assertIn("LEGAL PRECEDENTS", assembled.context_block)
        self.assertIn("USER RTI QUERY", assembled.query_block)
        self.assertEqual(assembled.sources_used[0], "CIC/1")
        self.assertIn("COMMISSION_FINDINGS", assembled.chunk_types_used)
        self.assertLess(
            assembled.context_block.index("COMMISSION_FINDINGS"),
            assembled.context_block.index("FULL_SUMMARY"),
        )

    def test_token_cap_truncates_context(self):
        long_text = "[COMMISSION_FINDINGS] " + ("personal information file noting disclosure " * 2000)
        chunks = [
            self._chunk(f"findings-{index}", f"CIC/{index}", "COMMISSION_FINDINGS", long_text, index)
            for index in range(1, 20)
        ]
        query = "Need analysis for Section 8(1)(j). " * 300
        assembled = ContextAssembler().assemble(query, chunks, "exemption_check")

        self.assertLessEqual(assembled.token_estimate, MAX_TOTAL_TOKENS)
        self.assertLessEqual(ContextAssembler._approx_tokens(assembled.query_block), QUERY_BLOCK_TOKENS + 20)
        self.assertTrue(assembled.sources_used)
        self.assertIn("...", assembled.full_prompt)

    def test_invalid_query_type_defaults(self):
        chunk = self._chunk("x", "CIC/X", "SECTION_ANALYSIS", "Section analysis text " * 20, 1)
        assembled = ContextAssembler().assemble("What should PIO do?", [chunk], "unknown")
        self.assertIn("PIO assistance request", assembled.query_block)


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestContextAssembler)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assemble Qwen-ready legal retrieval context.")
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
