"""
Qwen context assembly for CIC/SIC legal retrieval.

This module accepts RetrievedChunk objects from hybrid retrieval and formats a
bounded, citation-safe prompt for the existing local Qwen/Ollama integration.
It does not call an LLM.

Install requirements:
    pip install pydantic

Run embedded tests:
    python src/rag/context_assembler.py --test
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field, field_validator


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from retrieval.hybrid_retriever import RetrievedChunk


MAX_TOTAL_TOKENS = 6000
SYSTEM_TOKEN_BUDGET = 500
CONTEXT_TOKEN_BUDGET = 4500
QUERY_TOKEN_BUDGET = 500
RESERVE_TOKEN_BUDGET = 500

CONTEXT_HEADER = "LEGAL CONTEXT -- CIC/SIC DECISIONS\n\nThe following decisions are relevant to this query:"

CONTEXT_CHUNK_TEMPLATE = """[{rank}] Case: {case_number} | Date: {decision_date} | Source: {source}
Department: {department} | Outcome: {outcome}
Type: {chunk_type}

{text}"""

PIO_ASSISTANCE_SYSTEM_PROMPT = """You are a legal research and drafting assistant for Public Information Officers under the RTI Act, 2005.
Answer based ONLY on the provided RTI Act/CIC/SIC/court/circular context.
Cite every legal point with the case number or source title in brackets.
Never invent case numbers, facts, or statutory language not present in the context.
Do not recommend or select the final PIO decision. Present legal considerations for the PIO's independent determination.
End with: "This system provides legal research and drafting assistance only. The final decision under the RTI Act, 2005 remains the responsibility of the concerned PIO."
"""

EXEMPTION_CHECK_SYSTEM_PROMPT = """You are analyzing whether an RTI exemption under Section 8 applies.
Review the provided legal context to identify comparable exemption/disclosure reasoning.
Structure your response: (1) Applicable section, (2) Supporting legal references, (3) Arguments for disclosure, (4) Arguments for exemption, (5) PIO verification points.
Do not present a final decision.
"""

APPEAL_ANALYSIS_SYSTEM_PROMPT = """You are analyzing an RTI appeal scenario.
Review similar CIC/SIC/court references to identify precedent patterns and learning points for the PIO.
Structure: (1) Similar references, (2) Reasoning patterns, (3) PIO learning points, (4) Records or facts to verify.
Do not predict a final outcome or recommend a final statutory decision.
"""

SYSTEM_PROMPTS = {
    "pio_assistance": PIO_ASSISTANCE_SYSTEM_PROMPT.strip(),
    "exemption_check": EXEMPTION_CHECK_SYSTEM_PROMPT.strip(),
    "appeal_analysis": APPEAL_ANALYSIS_SYSTEM_PROMPT.strip(),
}

CHUNK_PRIORITY = {
    "COMMISSION_FINDINGS": 1,
    "SECTION_ANALYSIS": 2,
    "DIRECTIONS": 3,
    "PUBLIC_INTEREST": 4,
    "PENALTY_REASONING": 5,
    "RTI_REQUEST": 6,
    "FULL_SUMMARY": 7,
}


class AssembledContext(BaseModel):
    """Structured context payload for downstream Qwen analysis."""

    system_prompt: str
    context_block: str
    query_block: str
    full_prompt: str
    token_estimate: int = Field(ge=0, le=MAX_TOTAL_TOKENS)
    sources_used: list[str] = Field(default_factory=list)
    chunk_types_used: list[str] = Field(default_factory=list)

    @field_validator("system_prompt", "context_block", "query_block", "full_prompt")
    @classmethod
    def _clean_strings(cls, value: str) -> str:
        return str(value or "").strip()


class ContextAssembler:
    """Assemble retrieved chunks into a Qwen-sized legal prompt."""

    def __init__(
        self,
        max_total_tokens: int = MAX_TOTAL_TOKENS,
        system_token_budget: int = SYSTEM_TOKEN_BUDGET,
        context_token_budget: int = CONTEXT_TOKEN_BUDGET,
        query_token_budget: int = QUERY_TOKEN_BUDGET,
        reserve_token_budget: int = RESERVE_TOKEN_BUDGET,
    ):
        self.max_total_tokens = max_total_tokens
        self.system_token_budget = system_token_budget
        self.context_token_budget = context_token_budget
        self.query_token_budget = query_token_budget
        self.reserve_token_budget = reserve_token_budget

    def assemble(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        query_type: str = "pio_assistance",
    ) -> AssembledContext:
        """Return a bounded prompt package using only retrieved chunk sources."""
        normalized_type = self._normalize_query_type(query_type)
        system_prompt = self._truncate_to_tokens(
            SYSTEM_PROMPTS[normalized_type],
            self.system_token_budget,
        )
        query_block = self._build_query_block(query)

        context_budget = self._available_context_budget(system_prompt, query_block)
        selected_chunks = self._select_chunks(retrieved_chunks, context_budget)
        context_block = self._build_context_block(selected_chunks)

        full_prompt = self._join_prompt(system_prompt, context_block, query_block)
        token_estimate = self._estimate_tokens_for_parts(system_prompt, context_block, query_block)

        # Final guard: shrink context further if fixed prompt labels pushed the
        # total over the hard Qwen window.
        while token_estimate > self.max_total_tokens and selected_chunks:
            selected_chunks = self._drop_lowest_value_chunk(selected_chunks)
            context_block = self._build_context_block(selected_chunks)
            full_prompt = self._join_prompt(system_prompt, context_block, query_block)
            token_estimate = self._estimate_tokens_for_parts(system_prompt, context_block, query_block)

        return AssembledContext(
            system_prompt=system_prompt,
            context_block=context_block,
            query_block=query_block,
            full_prompt=full_prompt,
            token_estimate=min(token_estimate, self.max_total_tokens),
            sources_used=self._unique(chunk.case_number for chunk in selected_chunks),
            chunk_types_used=self._unique(chunk.chunk_type for chunk in selected_chunks),
        )

    def _select_chunks(
        self,
        retrieved_chunks: list[RetrievedChunk],
        context_token_budget: int,
    ) -> list[RetrievedChunk]:
        chunks = self._dedupe_chunks(retrieved_chunks)
        if not chunks or context_token_budget <= self._approx_tokens(CONTEXT_HEADER):
            return []

        selected: list[RetrievedChunk] = []
        selected_ids: set[str] = set()
        used_tokens = self._approx_tokens(CONTEXT_HEADER)

        # Always include the strongest COMMISSION_FINDINGS chunk when available.
        top_findings = self._top_commission_findings(chunks)
        if top_findings:
            fitted = self._fit_chunk(top_findings, len(selected) + 1, context_token_budget - used_tokens)
            if fitted:
                selected.append(fitted)
                selected_ids.add(fitted.chunk_id)
                used_tokens += self._approx_tokens(self._format_chunk(fitted, len(selected)))

        for chunk in self._selection_order(chunks):
            if chunk.chunk_id in selected_ids:
                continue
            remaining = context_token_budget - used_tokens
            if remaining <= 0:
                break
            fitted = self._fit_chunk(chunk, len(selected) + 1, remaining)
            if not fitted:
                continue
            selected.append(fitted)
            selected_ids.add(fitted.chunk_id)
            used_tokens += self._approx_tokens(self._format_chunk(fitted, len(selected)))

        # Final prompt context must be ordered by retrieval relevance.
        return self._relevance_order(selected)

    def _fit_chunk(
        self,
        chunk: RetrievedChunk,
        rank: int,
        remaining_tokens: int,
    ) -> Optional[RetrievedChunk]:
        if remaining_tokens <= 0:
            return None

        formatted = self._format_chunk(chunk, rank)
        formatted_tokens = self._approx_tokens(formatted)
        if formatted_tokens <= remaining_tokens:
            return chunk

        metadata_tokens = self._approx_tokens(formatted) - self._approx_tokens(chunk.text)
        text_budget = remaining_tokens - metadata_tokens - 3
        if text_budget < 30:
            return None

        truncated_text = self._truncate_to_tokens(chunk.text, text_budget)
        fitted = self._copy_chunk_with_text(chunk, truncated_text)
        if self._approx_tokens(self._format_chunk(fitted, rank)) <= remaining_tokens:
            return fitted
        return None

    def _build_context_block(self, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return CONTEXT_HEADER

        blocks = [CONTEXT_HEADER]
        for index, chunk in enumerate(chunks, start=1):
            blocks.append(self._format_chunk(chunk, index))
        return "\n\n".join(blocks).strip()

    def _build_query_block(self, query: str) -> str:
        query_text = self._truncate_to_tokens(
            self._clean_text(query),
            self.query_token_budget,
        )
        return f"USER RTI QUERY\n\n{query_text}".strip()

    @staticmethod
    def _join_prompt(system_prompt: str, context_block: str, query_block: str) -> str:
        return f"{system_prompt}\n\n{context_block}\n\n{query_block}".strip()

    @staticmethod
    def _format_chunk(chunk: RetrievedChunk, rank: int) -> str:
        return CONTEXT_CHUNK_TEMPLATE.format(
            rank=rank,
            case_number=chunk.case_number or "N/A",
            decision_date=chunk.decision_date or "N/A",
            source=chunk.source or "N/A",
            department=chunk.department or "N/A",
            outcome=chunk.outcome or "N/A",
            chunk_type=chunk.chunk_type or "N/A",
            text=ContextAssembler._clean_text(chunk.text),
        ).strip()

    @staticmethod
    def _normalize_query_type(query_type: str) -> str:
        value = str(query_type or "pio_assistance").strip().lower()
        return value if value in SYSTEM_PROMPTS else "pio_assistance"

    def _available_context_budget(self, system_prompt: str, query_block: str) -> int:
        fixed_tokens = self._estimate_tokens_for_parts(system_prompt, "", query_block)
        hard_available = self.max_total_tokens - self.reserve_token_budget - fixed_tokens
        return max(0, min(self.context_token_budget, hard_available))

    @staticmethod
    def _selection_order(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return sorted(
            chunks,
            key=lambda chunk: (
                CHUNK_PRIORITY.get(chunk.chunk_type, 999),
                -float(chunk.rrf_score or 0.0),
                chunk.rank,
                chunk.case_number,
            ),
        )

    @staticmethod
    def _relevance_order(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return sorted(
            chunks,
            key=lambda chunk: (
                -float(chunk.rrf_score or 0.0),
                chunk.rank,
                CHUNK_PRIORITY.get(chunk.chunk_type, 999),
                chunk.case_number,
            ),
        )

    @staticmethod
    def _top_commission_findings(chunks: list[RetrievedChunk]) -> Optional[RetrievedChunk]:
        findings = [chunk for chunk in chunks if chunk.chunk_type == "COMMISSION_FINDINGS"]
        if not findings:
            return None
        return ContextAssembler._relevance_order(findings)[0]

    @staticmethod
    def _drop_lowest_value_chunk(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if len(chunks) <= 1:
            return chunks
        removable = sorted(
            chunks,
            key=lambda chunk: (
                1 if chunk.chunk_type == "COMMISSION_FINDINGS" else 0,
                -CHUNK_PRIORITY.get(chunk.chunk_type, 999),
                float(chunk.rrf_score or 0.0),
                -chunk.rank,
            ),
        )
        drop_id = removable[0].chunk_id
        return [chunk for chunk in chunks if chunk.chunk_id != drop_id]

    @staticmethod
    def _dedupe_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        best_by_id: dict[str, RetrievedChunk] = {}
        for chunk in chunks or []:
            if not chunk.text or not chunk.chunk_id:
                continue
            existing = best_by_id.get(chunk.chunk_id)
            if existing is None or float(chunk.rrf_score or 0.0) > float(existing.rrf_score or 0.0):
                best_by_id[chunk.chunk_id] = chunk
        return list(best_by_id.values())

    @staticmethod
    def _copy_chunk_with_text(chunk: RetrievedChunk, text: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk.chunk_id,
            case_number=chunk.case_number,
            source=chunk.source,
            chunk_type=chunk.chunk_type,
            text=text,
            decision_date=chunk.decision_date,
            outcome=chunk.outcome,
            department=chunk.department,
            metadata=chunk.metadata,
            bm25_score=chunk.bm25_score,
            vector_score=chunk.vector_score,
            rrf_score=chunk.rrf_score,
            rank=chunk.rank,
        )

    @staticmethod
    def _truncate_to_tokens(text: str, token_budget: int) -> str:
        original = str(text or "").strip()
        if token_budget <= 0:
            return ""
        if ContextAssembler._approx_tokens(original) <= token_budget:
            return original

        text = ContextAssembler._clean_text(original)
        max_words = max(1, int(token_budget / 1.3))
        words = text.split()
        result = " ".join(words[:max_words]).strip()
        return result.rstrip(" .,;:") + " ..."

    @staticmethod
    def _clean_text(text: str) -> str:
        return " ".join(str(text or "").replace("\x00", " ").split()).strip()

    @staticmethod
    def _approx_tokens(text: str) -> int:
        return int(round(len(str(text or "").split()) * 1.3))

    @classmethod
    def _estimate_tokens_for_parts(cls, system_prompt: str, context_block: str, query_block: str) -> int:
        # The user requirement defines token_estimate as len(text.split()) * 1.3
        # for all included prompt text. Newline labels are included because Qwen
        # receives the full assembled prompt.
        return cls._approx_tokens(f"{system_prompt} {context_block} {query_block}")

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result


class TestContextAssembler(unittest.TestCase):
    def _chunk(
        self,
        index: int,
        chunk_type: str,
        score: float,
        text_words: int = 160,
    ) -> RetrievedChunk:
        text = f"[{chunk_type}] " + ("section 8 file noting disclosure precedent " * text_words)
        return RetrievedChunk(
            chunk_id=f"chunk-{index}",
            case_number=f"CIC/TEST/A/2024/{index:06d}",
            source="CIC",
            chunk_type=chunk_type,
            text=text,
            decision_date="2024-01-01",
            outcome="PARTIAL",
            department="Revenue",
            bm25_score=10.0 - index,
            vector_score=score,
            rrf_score=score,
            rank=index,
        )

    def test_ten_chunks_respect_token_limit_and_sources(self):
        chunk_types = [
            "FULL_SUMMARY",
            "RTI_REQUEST",
            "DIRECTIONS",
            "COMMISSION_FINDINGS",
            "PUBLIC_INTEREST",
            "SECTION_ANALYSIS",
            "PENALTY_REASONING",
            "COMMISSION_FINDINGS",
            "DIRECTIONS",
            "FULL_SUMMARY",
        ]
        chunks = [
            self._chunk(index + 1, chunk_type, score=1.0 - (index * 0.05))
            for index, chunk_type in enumerate(chunk_types)
        ]

        assembled = ContextAssembler().assemble(
            query="Can file notings be denied under Section 8(1)(j)? " * 120,
            retrieved_chunks=chunks,
            query_type="exemption_check",
        )

        self.assertLessEqual(assembled.token_estimate, MAX_TOTAL_TOKENS)
        self.assertIn("LEGAL CONTEXT -- CIC/SIC DECISIONS", assembled.context_block)
        self.assertIn("COMMISSION_FINDINGS", assembled.chunk_types_used)
        self.assertTrue(all(source in assembled.context_block for source in assembled.sources_used))
        self.assertIn(EXEMPTION_CHECK_SYSTEM_PROMPT.strip(), assembled.system_prompt)

        source_positions = [
            assembled.context_block.index(case_number)
            for case_number in assembled.sources_used
        ]
        self.assertEqual(source_positions, sorted(source_positions))

    def test_query_types_produce_different_system_prompts(self):
        chunk = self._chunk(1, "COMMISSION_FINDINGS", 0.9, text_words=20)
        assembler = ContextAssembler()

        pio = assembler.assemble("query", [chunk], "pio_assistance")
        exemption = assembler.assemble("query", [chunk], "exemption_check")
        appeal = assembler.assemble("query", [chunk], "appeal_analysis")

        self.assertNotEqual(pio.system_prompt, exemption.system_prompt)
        self.assertNotEqual(exemption.system_prompt, appeal.system_prompt)
        self.assertIn("legal research and drafting assistance only", pio.system_prompt)
        self.assertIn("Section 8", exemption.system_prompt)
        self.assertIn("appeal scenario", appeal.system_prompt)


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestContextAssembler)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assemble legal context for Qwen RTI analysis.")
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
