"""
Reference retrieval pipeline for RTI legal research assistance.

This module returns compact reference cards for the UI. It does not generate
the PIO draft and it never decides the final RTI outcome.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from retrieval.hybrid_retriever import HybridRetriever, RetrievedChunk


logger = logging.getLogger(__name__)

CHUNK_TYPE_PRIORITY = {
    "PRECEDENT_SUMMARY": 1,
    "COMMISSION_OBSERVATION": 2,
    "COMMISSION_OBSERVATIONS": 2,
    "COMMISSION_FINDINGS": 2,
    "FINAL_ORDER": 3,
    "PIO_LEARNING_SIGNAL": 4,
    "INFORMATION_REQUESTED": 5,
    "FACTS": 6,
    "ENTITY_CONTEXT": 7,
}

COMMITTEE_QUERY_RE = re.compile(
    r"(?i)\b(committee|report|proceedings?|members?|compliance|follow\s+up|status)\b"
)


class ReferenceCard(BaseModel):
    source_type: str
    title_or_case_number: str
    case_number: str = ""
    public_authority: str = ""
    outcome: str = ""
    relevant_section: str = ""
    extracted_passage: str
    why_relevant: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_type", "title_or_case_number", "case_number", "public_authority", "outcome", "relevant_section", "extracted_passage", "why_relevant")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return " ".join(str(value or "").split()).strip()


class ReferenceRetriever:
    """Hybrid retrieval plus rule-based legal reranking."""

    def __init__(self, retriever: Optional[HybridRetriever] = None, max_pool: int = 30):
        self.retriever = retriever or HybridRetriever()
        self.max_pool = max_pool

    def retrieve(
        self,
        raw_text: str,
        extracted_parameters: dict[str, Any],
        sections: Optional[list[str]] = None,
        department_context: str = "",
        outcome_hint: str = "",
        limit: int = 8,
    ) -> list[ReferenceCard]:
        query = self._build_query(raw_text, extracted_parameters, sections, department_context)
        chunks = self._search_all(query)
        ranked = self._rerank(
            chunks=chunks,
            raw_text=raw_text,
            sections=sections or [],
            department_context=department_context,
            outcome_hint=outcome_hint,
            info_type=str(extracted_parameters.get("classification_type") or extracted_parameters.get("information_type") or ""),
        )
        cards: list[ReferenceCard] = []
        seen_titles: set[str] = set()
        for score, chunk, reasons in ranked:
            metadata = dict(chunk.metadata or {})
            title = chunk.case_number or str(metadata.get("case_number") or f"{chunk.source} reference")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            summary = self._case_summary(chunk, metadata)
            cards.append(
                ReferenceCard(
                    source_type=self._source_type(chunk),
                    title_or_case_number=title,
                    case_number=chunk.case_number,
                    public_authority=str(metadata.get("public_authority") or chunk.public_authority or chunk.department or ""),
                    outcome=str(metadata.get("outcome") or chunk.outcome or ""),
                    relevant_section=self._section(chunk),
                    extracted_passage=self._compact(chunk.text, 620),
                    why_relevant=summary,
                    confidence_score=round(max(0.0, min(1.0, score)), 3),
                    metadata={
                        "chunk_type": chunk.chunk_type,
                        "date": metadata.get("date") or metadata.get("decision_date") or chunk.decision_date,
                        "hearing_date": metadata.get("hearing_date") or chunk.hearing_date,
                        "commissioner": metadata.get("commissioner") or chunk.commissioner,
                        "reasoning_pattern": metadata.get("reasoning_pattern") or chunk.reasoning_pattern,
                        "pio_learning_signal": metadata.get("pio_learning_signal") or chunk.pio_learning_signal,
                        "rti_sections": metadata.get("rti_sections") or metadata.get("sections_invoked") or [],
                        "exemption_sections": metadata.get("exemption_sections") or [],
                        "relevance_reason": "; ".join(reasons),
                    },
                )
            )
            if len(cards) >= limit:
                break
        return cards

    def _search_all(self, query: str) -> list[RetrievedChunk]:
        results: list[RetrievedChunk] = []
        for mode in ("hybrid", "bm25"):
            try:
                results.extend(self.retriever.search(query, n_results=self.max_pool, search_mode=mode))
            except Exception as exc:
                logger.warning("Reference retrieval mode failed | mode=%s error=%s", mode, exc)
        by_id: dict[str, RetrievedChunk] = {}
        for chunk in results:
            existing = by_id.get(chunk.chunk_id)
            if existing is None or float(chunk.rrf_score or 0.0) > float(existing.rrf_score or 0.0):
                by_id[chunk.chunk_id] = chunk
        return list(by_id.values())

    def _rerank(
        self,
        chunks: list[RetrievedChunk],
        raw_text: str,
        sections: list[str],
        department_context: str,
        outcome_hint: str,
        info_type: str,
    ) -> list[tuple[float, RetrievedChunk, list[str]]]:
        section_set = {self._norm(section) for section in sections if section}
        dept = department_context.lower()
        outcome = outcome_hint.lower()
        info = info_type.lower()
        committee_query = bool(COMMITTEE_QUERY_RE.search(" ".join([raw_text, info, department_context])))
        ranked: list[tuple[float, RetrievedChunk, list[str]]] = []
        for chunk in chunks:
            metadata = getattr(chunk, "metadata", {}) if hasattr(chunk, "metadata") else {}
            text_blob = " ".join([
                chunk.text or "",
                chunk.case_number or "",
                chunk.department or "",
                chunk.outcome or "",
                str(metadata),
            ]).lower()
            priority = CHUNK_TYPE_PRIORITY.get(chunk.chunk_type, 99)
            score = 0.45 * float(chunk.rrf_score or 0.0)
            if priority < 99:
                score += max(0.0, 0.22 - (priority - 1) * 0.025)
            reasons: list[str] = []
            if section_set and any(section in self._norm(text_blob) for section in section_set):
                score += 0.20
                reasons.append("matched relevant RTI Act section")
            if dept and dept.lower() in text_blob:
                score += 0.12
                reasons.append("matched department or public authority context")
            if outcome and outcome in text_blob:
                score += 0.08
                reasons.append("matched outcome pattern")
            if info and info.replace("_", " ") in text_blob:
                score += 0.06
                reasons.append("matched information type")
            if priority < 99:
                reasons.append(f"strong legal chunk type: {chunk.chunk_type}")
            if committee_query and chunk.chunk_type in {
                "PRECEDENT_SUMMARY",
                "COMMISSION_OBSERVATION",
                "COMMISSION_OBSERVATIONS",
                "COMMISSION_FINDINGS",
                "FINAL_ORDER",
                "PIO_LEARNING_SIGNAL",
            }:
                score += 0.12
                reasons.append("committee/report query boosted commission reasoning")
            if committee_query and chunk.chunk_type in {"RTI_REQUEST", "INFORMATION_REQUESTED", "FACTS"}:
                score -= 0.04
            ranked.append((max(0.0, min(score, 1.0)), chunk, reasons))
        return sorted(
            ranked,
            key=lambda item: (
                -item[0],
                CHUNK_TYPE_PRIORITY.get(item[1].chunk_type, 99),
                item[1].rank,
                item[1].case_number,
            ),
        )

    @staticmethod
    def _build_query(raw_text: str, extracted_parameters: dict[str, Any], sections: Optional[list[str]], department_context: str) -> str:
        entities = ", ".join(extracted_parameters.get("entities") or extracted_parameters.get("extracted_entities") or [])
        systems = ", ".join(extracted_parameters.get("systems") or [])
        info_type = extracted_parameters.get("classification_type") or extracted_parameters.get("information_type") or ""
        return "\n".join(
            part for part in [
                raw_text,
                f"Information type: {info_type}",
                f"Systems: {systems}",
                f"Entities: {entities}",
                f"Department/public authority: {department_context}",
                f"RTI Act sections: {', '.join(sections or [])}",
            ]
            if part and part.strip()
        )

    @staticmethod
    def _source_type(chunk: RetrievedChunk) -> str:
        source = (chunk.source or "").upper()
        if not source and chunk.metadata:
            source = str(chunk.metadata.get("source_type") or chunk.metadata.get("source") or "").upper()
        if source == "SIC":
            return "SIC Decision"
        if source == "COURT":
            return "Court Judgment"
        if source == "CIRCULAR":
            return "Department Circular"
        if source == "RTI_ACT":
            return "RTI Act, 2005"
        if source == "PREVIOUS_RTI":
            return "Previous RTI Case"
        return "CIC Decision" if source == "CIC" else "Legal Reference"

    @staticmethod
    def _section(chunk: RetrievedChunk) -> str:
        text = chunk.text or ""
        match = re.search(r"(?i)\b(?:Section|Sec\.?|S\.|u/s)\s*([0-9]+(?:\([0-9a-z]\))?(?:\([a-z]\))?)", text)
        return re.sub(r"\s+", "", match.group(1)) if match else ""

    @staticmethod
    def _compact(text: str, limit: int) -> str:
        text = " ".join(str(text or "").split())
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."

    @classmethod
    def _case_summary(cls, chunk: RetrievedChunk, metadata: dict[str, Any]) -> str:
        """Return a short user-facing summary so a PIO can judge relevance quickly."""
        text = cls._strip_chunk_label(chunk.text or "")
        reasoning = cls._metadata_text(metadata.get("reasoning_pattern") or chunk.reasoning_pattern)
        learning = cls._metadata_text(metadata.get("pio_learning_signal") or chunk.pio_learning_signal)
        outcome = str(metadata.get("outcome") or chunk.outcome or "").replace("_", " ").title()
        authority = str(metadata.get("public_authority") or chunk.public_authority or chunk.department or "").strip()

        if chunk.chunk_type in {"PRECEDENT_SUMMARY", "FULL_SUMMARY"} and text:
            base = text
        elif chunk.chunk_type in {"COMMISSION_OBSERVATION", "COMMISSION_OBSERVATIONS", "COMMISSION_FINDINGS", "FINAL_ORDER"}:
            base = f"Commission reasoning: {text}"
        elif chunk.chunk_type in {"RTI_REQUEST", "INFORMATION_REQUESTED", "FACTS"}:
            base = f"Request context: {text}"
        elif chunk.chunk_type == "PIO_LEARNING_SIGNAL":
            base = f"PIO learning: {text}"
        else:
            base = text

        extras = []
        if authority:
            extras.append(f"Authority: {authority}")
        if outcome:
            extras.append(f"Outcome: {outcome}")
        if reasoning:
            extras.append(f"Pattern: {reasoning}")
        elif learning:
            extras.append(f"PIO signal: {learning}")

        summary = cls._compact(base, 260)
        if extras:
            summary = f"{summary} {' | '.join(extras[:2])}."
        return cls._compact(summary, 360)

    @staticmethod
    def _strip_chunk_label(text: str) -> str:
        return re.sub(r"^\s*\[[A-Z_]+\]\s*", "", " ".join(str(text or "").split())).strip()

    @staticmethod
    def _metadata_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return "; ".join(str(item).strip() for item in value if str(item).strip())
        return str(value).strip()

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"\s+", "", str(text or "").lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieve compact RTI legal reference cards.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--department-hint", default="")
    parser.add_argument("--section", action="append", default=[])
    args = parser.parse_args()
    cards = ReferenceRetriever().retrieve(
        raw_text=args.text,
        extracted_parameters={},
        sections=args.section,
        department_context=args.department_hint,
    )
    print(json.dumps([card.model_dump() for card in cards], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
