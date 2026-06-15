"""
RTI analysis orchestration over hybrid retrieval + Qwen reasoning.

The engine coordinates:
1. Department routing through the existing backend routing module.
2. Hybrid CIC/SIC/circular retrieval.
3. Context assembly for Qwen.
4. Local Qwen reasoning via the existing Ollama chat pattern.

Facts must come from retrieved chunks. If retrieval returns no similar cases,
the engine lowers confidence and states that clearly.

Install requirements:
    pip install pydantic ollama

Run embedded tests:
    python src/engine/rti_analysis_engine.py --test
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for path in (SRC_DIR, PROJECT_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from rag.context_assembler import ContextAssembler
from retrieval.hybrid_retriever import HybridRetriever, RetrievedChunk


logger = logging.getLogger(__name__)

QWEN_MODEL = os.getenv("QWEN_MODEL", os.getenv("OLLAMA_QWEN_MODEL", "qwen2.5:14b"))

ANALYSIS_TYPE_TO_QUERY_TYPE = {
    "pio_check": "pio_assistance",
    "appeal_prediction": "appeal_analysis",
    "exemption_check": "exemption_check",
}

SECTION_RE = re.compile(
    r"(?i)\b(?:Section\s*)?("
    r"6\s*\(\s*3\s*\)|"
    r"7\s*(?:\(\s*1\s*\))?|"
    r"8\s*\(\s*1\s*\)\s*\(\s*[a-j]\s*\)|"
    r"8\s*\(\s*2\s*\)|"
    r"8\s*\(\s*1\s*\)|"
    r"9|10|11|19\s*(?:\(\s*1\s*\)|\(\s*3\s*\))?|20\s*(?:\(\s*1\s*\))?|24"
    r")(?=\W|$)"
)


class ExemptionRisk(BaseModel):
    section: str
    risk_level: str = Field(pattern=r"^(HIGH|MEDIUM|LOW)$")
    reasoning: str
    cic_precedent: str

    @field_validator("section", "reasoning", "cic_precedent")
    @classmethod
    def _clean_required_text(cls, value: str) -> str:
        return str(value or "").strip()


class SimilarCase(BaseModel):
    case_number: str
    decision_date: str = ""
    outcome: str = ""
    similarity_score: float = Field(ge=0.0, le=1.0)
    key_finding: str

    @field_validator("case_number", "decision_date", "outcome", "key_finding")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return str(value or "").strip()


class RTIAnalysisResult(BaseModel):
    department: str
    detected_sections: list[str] = Field(default_factory=list)
    exemption_risks: list[ExemptionRisk] = Field(default_factory=list)
    similar_cases: list[SimilarCase] = Field(default_factory=list)
    relevant_circulars: list[str] = Field(default_factory=list)
    recommendation: str
    recommendation_confidence: float = Field(ge=0.0, le=1.0)
    draft_response_hint: str
    sources_cited: list[str] = Field(default_factory=list)
    analysis_type: str
    processing_time_seconds: float = Field(ge=0.0)


class RTIAnalysisEngine:
    """Coordinate RTI query analysis using retrieval as the factual layer."""

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        context_assembler: Optional[ContextAssembler] = None,
        qwen_model: str = QWEN_MODEL,
        qwen_client: Any = None,
        department_classifier: Any = None,
        max_retrieval_results: int = 12,
    ):
        self.retriever = retriever if retriever is not None else HybridRetriever()
        self.context_assembler = context_assembler if context_assembler is not None else ContextAssembler()
        self.qwen_model = qwen_model
        self.qwen_client = qwen_client
        self.department_classifier = department_classifier
        self.max_retrieval_results = max_retrieval_results

    def analyze(
        self,
        rti_text: Optional[str] = None,
        analysis_type: str = "pio_check",
        department_hint: Optional[str] = None,
        **kwargs: Any,
    ) -> RTIAnalysisResult:
        """
        Run the complete RTI analysis pipeline.

        The user specification names the first parameter `rtl_text`; that alias
        is also accepted through kwargs for compatibility.
        """
        start = time.perf_counter()
        text = (rti_text if rti_text is not None else kwargs.get("rtl_text", "") or "").strip()
        normalized_type = self._normalize_analysis_type(analysis_type)

        if not text:
            return self._empty_result(
                department=department_hint or "Unknown",
                analysis_type=normalized_type,
                processing_time=time.perf_counter() - start,
                reason="No RTI text was provided for analysis.",
            )

        department = department_hint or self._detect_department(text)
        detected_sections = self._detect_sections(text)
        rti_category = self._classify_rti_type(text)

        retrieved_chunks = self._retrieve_decisions(text, detected_sections, normalized_type)
        circular_chunks = self._retrieve_circulars(text)
        all_chunks = self._merge_chunks(retrieved_chunks, circular_chunks)

        query_type = ANALYSIS_TYPE_TO_QUERY_TYPE[normalized_type]
        assembled_context = self.context_assembler.assemble(
            query=self._query_with_parameters(text, detected_sections, rti_category, department),
            retrieved_chunks=all_chunks,
            query_type=query_type,
        )

        qwen_data = self._reason_with_qwen(assembled_context.full_prompt, assembled_context.sources_used)

        similar_cases = self._build_similar_cases(retrieved_chunks, assembled_context.sources_used)
        relevant_circulars = self._build_relevant_circulars(circular_chunks, assembled_context.sources_used)
        exemption_risks = self._build_exemption_risks(
            detected_sections=detected_sections,
            chunks=retrieved_chunks,
            qwen_data=qwen_data,
            allowed_sources=assembled_context.sources_used,
        )
        recommendation, draft_hint = self._build_recommendation_text(
            qwen_data=qwen_data,
            similar_cases=similar_cases,
            department=department,
            detected_sections=detected_sections,
        )
        confidence = self._confidence(similar_cases, qwen_data, retrieved_chunks)
        sources_cited = self._sources_cited(assembled_context.sources_used, similar_cases, exemption_risks)

        return RTIAnalysisResult(
            department=department,
            detected_sections=detected_sections,
            exemption_risks=exemption_risks,
            similar_cases=similar_cases,
            relevant_circulars=relevant_circulars,
            recommendation=recommendation,
            recommendation_confidence=confidence,
            draft_response_hint=draft_hint,
            sources_cited=sources_cited,
            analysis_type=normalized_type,
            processing_time_seconds=round(time.perf_counter() - start, 3),
        )

    def _detect_department(self, text: str) -> str:
        if self.department_classifier is not None:
            try:
                result = self.department_classifier(text)
                return self._department_from_result(result)
            except Exception as exc:
                logger.warning("Injected department classifier failed: %s", exc)

        try:
            from routing import classify_department

            result = classify_department(text)
            return self._department_from_result(result)
        except Exception as exc:
            logger.warning("Department routing failed; using Unknown: %s", exc)
            return "Unknown"

    def _retrieve_decisions(
        self,
        text: str,
        detected_sections: list[str],
        analysis_type: str,
    ) -> list[RetrievedChunk]:
        query = self._retrieval_query(text, detected_sections)
        results: list[RetrievedChunk] = []

        try:
            results.extend(
                self.retriever.search(
                    query,
                    n_results=self.max_retrieval_results,
                    filters={"chunk_type": "COMMISSION_FINDINGS"},
                    search_mode="commission_findings",
                )
            )
        except Exception as exc:
            logger.warning("Commission findings retrieval failed: %s", exc)

        if analysis_type in {"pio_check", "appeal_prediction"}:
            try:
                results.extend(
                    self.retriever.search(
                        query,
                        n_results=max(5, self.max_retrieval_results // 2),
                        search_mode="hybrid",
                    )
                )
            except Exception as exc:
                logger.warning("Hybrid retrieval failed: %s", exc)

        return self._merge_chunks(results)

    def _retrieve_circulars(self, text: str) -> list[RetrievedChunk]:
        try:
            return self.retriever.search(
                text,
                n_results=5,
                filters={"source": "CIRCULAR"},
                search_mode="circulars",
            )
        except Exception as exc:
            logger.warning("Circular retrieval failed: %s", exc)
            return []

    def _reason_with_qwen(self, full_prompt: str, allowed_sources: list[str]) -> dict[str, Any]:
        if not allowed_sources:
            return {
                "recommendation": "No similar CIC/SIC decisions were retrieved. Manual legal review is recommended.",
                "draft_response_hint": "Do not cite precedents because none were retrieved. Record that the recommendation is low-confidence.",
                "exemption_risks": [],
            }

        prompt = self._qwen_prompt(full_prompt, allowed_sources)
        try:
            client = self.qwen_client
            if client is None:
                import ollama as _ollama_client

                client = _ollama_client

            # Existing project Qwen call pattern:
            # ollama.chat(model=..., messages=[{"role": "user", "content": prompt}], format="json", options=...)
            response = client.chat(
                model=self.qwen_model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={
                    "temperature": 0.0,
                    "num_predict": 900,
                },
            )
            content = response.get("message", {}).get("content", "")
            parsed = json.loads(self._clean_json(content))
            return self._sanitize_qwen_payload(parsed, allowed_sources)
        except Exception as exc:
            logger.warning("Qwen reasoning failed; using retrieval-only fallback: %s", exc)
            return {
                "recommendation": "Qwen reasoning was unavailable. Use retrieved CIC/SIC cases for manual review.",
                "draft_response_hint": "Review the cited similar cases and decide disclosure, partial disclosure, transfer, or rejection under the RTI Act.",
                "exemption_risks": [],
            }

    @staticmethod
    def _qwen_prompt(full_prompt: str, allowed_sources: list[str]) -> str:
        sources = ", ".join(allowed_sources)
        return f"""{full_prompt}

STRUCTURED OUTPUT
Return ONLY one JSON object. No markdown. No explanation outside JSON.
Facts and citations must come ONLY from these retrieved case numbers:
{sources}

JSON schema:
{{
  "recommendation": "main recommendation text",
  "draft_response_hint": "actionable points for the PIO response",
  "exemption_risks": [
    {{
      "section": "8(1)(j)",
      "risk_level": "HIGH | MEDIUM | LOW",
      "reasoning": "why the exemption may apply",
      "cic_precedent": "one case number from the allowed source list"
    }}
  ]
}}
"""

    def _sanitize_qwen_payload(self, parsed: dict[str, Any], allowed_sources: list[str]) -> dict[str, Any]:
        allowed = set(allowed_sources)
        risks: list[dict[str, Any]] = []
        for item in parsed.get("exemption_risks", []) or []:
            precedent = str(item.get("cic_precedent", "")).strip()
            if precedent not in allowed:
                continue
            section = self._normalize_section(str(item.get("section", "")))
            if not section:
                continue
            risk_level = str(item.get("risk_level", "MEDIUM")).strip().upper()
            if risk_level not in {"HIGH", "MEDIUM", "LOW"}:
                risk_level = "MEDIUM"
            risks.append(
                {
                    "section": section,
                    "risk_level": risk_level,
                    "reasoning": self._clean_text(item.get("reasoning", "")) or "Risk inferred from retrieved CIC/SIC precedent.",
                    "cic_precedent": precedent,
                }
            )

        return {
            "recommendation": self._clean_text(parsed.get("recommendation", "")),
            "draft_response_hint": self._clean_text(parsed.get("draft_response_hint", "")),
            "exemption_risks": risks,
        }

    def _build_similar_cases(
        self,
        chunks: list[RetrievedChunk],
        allowed_sources: list[str],
    ) -> list[SimilarCase]:
        allowed = set(allowed_sources)
        cases: list[SimilarCase] = []
        seen: set[str] = set()
        for chunk in sorted(chunks, key=lambda item: (-float(item.rrf_score or 0.0), item.rank)):
            if chunk.case_number not in allowed or chunk.case_number in seen:
                continue
            seen.add(chunk.case_number)
            cases.append(
                SimilarCase(
                    case_number=chunk.case_number,
                    decision_date=chunk.decision_date or "",
                    outcome=chunk.outcome or "",
                    similarity_score=max(0.0, min(1.0, float(chunk.rrf_score or 0.0))),
                    key_finding=self._first_sentence(chunk.text),
                )
            )
            if len(cases) >= 5:
                break
        return cases

    def _build_relevant_circulars(
        self,
        circular_chunks: list[RetrievedChunk],
        allowed_sources: list[str],
    ) -> list[str]:
        allowed = set(allowed_sources)
        circulars: list[str] = []
        seen: set[str] = set()
        for chunk in circular_chunks:
            if chunk.case_number not in allowed or chunk.case_number in seen:
                continue
            seen.add(chunk.case_number)
            circulars.append(chunk.case_number)
        return circulars

    def _build_exemption_risks(
        self,
        detected_sections: list[str],
        chunks: list[RetrievedChunk],
        qwen_data: dict[str, Any],
        allowed_sources: list[str],
    ) -> list[ExemptionRisk]:
        risks: list[ExemptionRisk] = []
        seen: set[tuple[str, str]] = set()
        for item in qwen_data.get("exemption_risks", []) or []:
            key = (item["section"], item["cic_precedent"])
            if key in seen:
                continue
            seen.add(key)
            risks.append(ExemptionRisk(**item))

        if risks:
            return risks

        allowed = set(allowed_sources)
        sections = detected_sections or self._sections_from_chunks(chunks)
        precedent_by_section = self._precedent_by_section(chunks, allowed)
        for section in sections:
            precedent = precedent_by_section.get(section)
            if not precedent:
                continue
            risks.append(
                ExemptionRisk(
                    section=section,
                    risk_level="MEDIUM" if section.startswith("8") else "LOW",
                    reasoning=f"Section {section} appears in retrieved CIC/SIC reasoning for a similar RTI issue.",
                    cic_precedent=precedent.case_number,
                )
            )
        return risks

    def _build_recommendation_text(
        self,
        qwen_data: dict[str, Any],
        similar_cases: list[SimilarCase],
        department: str,
        detected_sections: list[str],
    ) -> tuple[str, str]:
        recommendation = qwen_data.get("recommendation") or ""
        draft_hint = qwen_data.get("draft_response_hint") or ""

        if not similar_cases:
            recommendation = (
                "No similar CIC/SIC decisions were retrieved. Treat this as low-confidence and conduct manual legal review "
                f"before issuing the RTI response for {department}."
            )
            draft_hint = (
                "Acknowledge the request, verify record custody, identify any applicable RTI Act sections, and avoid citing "
                "precedents because none were retrieved."
            )
            return recommendation, draft_hint

        if not recommendation:
            sections_text = ", ".join(detected_sections) if detected_sections else "no explicit exemption section"
            recommendation = (
                f"Review the retrieved CIC/SIC precedents before responding. Detected sections: {sections_text}. "
                f"Most similar case: {similar_cases[0].case_number}."
            )
        if not draft_hint:
            draft_hint = (
                "Cite the retrieved case numbers, explain whether the requested records are held by the department, "
                "and consider disclosure with severance where exempt material can be redacted."
            )
        return recommendation, draft_hint

    @staticmethod
    def _confidence(
        similar_cases: list[SimilarCase],
        qwen_data: dict[str, Any],
        retrieved_chunks: list[RetrievedChunk],
    ) -> float:
        if not similar_cases:
            return 0.25
        score = 0.45
        score += min(0.30, len(similar_cases) * 0.06)
        score += min(0.15, len(retrieved_chunks) * 0.015)
        if qwen_data.get("recommendation"):
            score += 0.10
        return round(min(score, 0.95), 2)

    @staticmethod
    def _sources_cited(
        assembled_sources: list[str],
        similar_cases: list[SimilarCase],
        exemption_risks: list[ExemptionRisk],
    ) -> list[str]:
        cited = [case.case_number for case in similar_cases]
        cited.extend(risk.cic_precedent for risk in exemption_risks)
        allowed = set(assembled_sources)
        return RTIAnalysisEngine._unique(source for source in cited if source in allowed)

    @staticmethod
    def _detect_sections(text: str) -> list[str]:
        sections: list[str] = []
        for match in SECTION_RE.finditer(text or ""):
            section = RTIAnalysisEngine._normalize_section(match.group(1))
            if section and section not in sections:
                sections.append(section)
        return sections

    @staticmethod
    def _normalize_section(value: str) -> str:
        text = re.sub(r"\s+", "", str(value or "").lower())
        text = text.replace("section", "")
        if not text:
            return ""
        if re.fullmatch(r"\d+", text):
            return text
        return text

    @staticmethod
    def _classify_rti_type(text: str) -> str:
        lower = (text or "").lower()
        if any(term in lower for term in ("file noting", "note sheet", "file note")):
            return "file_request"
        if any(term in lower for term in ("service book", "salary", "medical", "personal", "employee")):
            return "personal_records"
        if any(term in lower for term in ("tender", "contract", "bid", "procurement")):
            return "procurement"
        if any(term in lower for term in ("source code", "server", "password", "security audit", "ip address")):
            return "technical_or_security"
        return "information_request"

    @staticmethod
    def _retrieval_query(text: str, detected_sections: list[str]) -> str:
        sections = " ".join(f"Section {section}" for section in detected_sections)
        return f"{text} {sections}".strip()

    @staticmethod
    def _query_with_parameters(text: str, sections: list[str], rti_category: str, department: str) -> str:
        section_text = ", ".join(sections) if sections else "None explicitly mentioned"
        return (
            f"Department: {department}\n"
            f"RTI type: {rti_category}\n"
            f"Sections mentioned: {section_text}\n\n"
            f"RTI text:\n{text}"
        )

    @staticmethod
    def _merge_chunks(*chunk_lists: list[RetrievedChunk]) -> list[RetrievedChunk]:
        by_id: dict[str, RetrievedChunk] = {}
        for chunks in chunk_lists:
            for chunk in chunks or []:
                existing = by_id.get(chunk.chunk_id)
                if existing is None or float(chunk.rrf_score or 0.0) > float(existing.rrf_score or 0.0):
                    by_id[chunk.chunk_id] = chunk
        return sorted(by_id.values(), key=lambda item: (-float(item.rrf_score or 0.0), item.rank))

    @staticmethod
    def _department_from_result(result: Any) -> str:
        if isinstance(result, str):
            return result
        for attr in ("department_name", "primary_department", "department"):
            value = getattr(result, attr, None)
            if value:
                return str(value)
        if isinstance(result, dict):
            return str(result.get("department_name") or result.get("primary_department") or result.get("department") or "Unknown")
        return "Unknown"

    @staticmethod
    def _sections_from_chunks(chunks: list[RetrievedChunk]) -> list[str]:
        sections: list[str] = []
        for chunk in chunks:
            for section in RTIAnalysisEngine._detect_sections(chunk.text):
                if section not in sections:
                    sections.append(section)
        return sections

    @staticmethod
    def _precedent_by_section(
        chunks: list[RetrievedChunk],
        allowed_sources: set[str],
    ) -> dict[str, RetrievedChunk]:
        mapping: dict[str, RetrievedChunk] = {}
        for chunk in sorted(chunks, key=lambda item: (-float(item.rrf_score or 0.0), item.rank)):
            if chunk.case_number not in allowed_sources:
                continue
            for section in RTIAnalysisEngine._detect_sections(chunk.text):
                mapping.setdefault(section, chunk)
        return mapping

    @staticmethod
    def _first_sentence(text: str) -> str:
        clean = RTIAnalysisEngine._clean_text(re.sub(r"^\[[A-Z_]+\]\s*", "", str(text or "")))
        if not clean:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", clean)
        return parts[0][:350].strip()

    @staticmethod
    def _clean_text(value: Any) -> str:
        return " ".join(str(value or "").replace("\x00", " ").split()).strip()

    @staticmethod
    def _clean_json(raw: str) -> str:
        raw = str(raw or "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end + 1]
        raw = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"```\s*$", "", raw)
        raw = re.sub(r",\s*([\]}])", r"\1", raw)
        return raw.strip()

    @staticmethod
    def _normalize_analysis_type(analysis_type: str) -> str:
        value = str(analysis_type or "pio_check").strip().lower()
        return value if value in ANALYSIS_TYPE_TO_QUERY_TYPE else "pio_check"

    @staticmethod
    def _unique(values) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    @staticmethod
    def _empty_result(
        department: str,
        analysis_type: str,
        processing_time: float,
        reason: str,
    ) -> RTIAnalysisResult:
        return RTIAnalysisResult(
            department=department,
            detected_sections=[],
            exemption_risks=[],
            similar_cases=[],
            relevant_circulars=[],
            recommendation=reason,
            recommendation_confidence=0.0,
            draft_response_hint="Provide RTI text or OCR output before running legal analysis.",
            sources_cited=[],
            analysis_type=analysis_type,
            processing_time_seconds=round(processing_time, 3),
        )


class FakeRetriever:
    def search(
        self,
        query: str,
        n_results: int = 10,
        filters: Optional[dict[str, Any]] = None,
        search_mode: str = "hybrid",
    ) -> list[RetrievedChunk]:
        if search_mode == "circulars" or (filters or {}).get("source") == "CIRCULAR":
            return [
                RetrievedChunk(
                    chunk_id="circular-1",
                    case_number="CIRCULAR/RTI/2024/01",
                    source="CIRCULAR",
                    chunk_type="FULL_SUMMARY",
                    text="Circular requires timely RTI response and reasoned speaking order.",
                    decision_date="2024-01-10",
                    outcome="PROCEDURAL",
                    department="DoPT",
                    rrf_score=0.7,
                    rank=1,
                )
            ]

        return [
            RetrievedChunk(
                chunk_id="case-1",
                case_number="CIC/TEST/A/2024/000001",
                source="CIC",
                chunk_type="COMMISSION_FINDINGS",
                text="[COMMISSION_FINDINGS] The Commission held that file notings are not automatically exempt under Section 8(1)(j) and disclosure may be made after redaction.",
                decision_date="2024-02-01",
                outcome="PARTIAL",
                department="Revenue",
                bm25_score=12.0,
                vector_score=0.95,
                rrf_score=0.95,
                rank=1,
            ),
            RetrievedChunk(
                chunk_id="case-2",
                case_number="CIC/TEST/A/2024/000002",
                source="CIC",
                chunk_type="COMMISSION_FINDINGS",
                text="[COMMISSION_FINDINGS] Personal records of employees may attract Section 8(1)(j) unless larger public interest is shown.",
                decision_date="2024-03-01",
                outcome="REJECTED",
                department="Revenue",
                bm25_score=9.0,
                vector_score=0.9,
                rrf_score=0.88,
                rank=2,
            ),
        ][:n_results]


class FakeQwenClient:
    def chat(self, model: str, messages: list[dict[str, str]], format: str, options: dict[str, Any]):
        return {
            "message": {
                "content": json.dumps(
                    {
                        "recommendation": "Disclose file notings after redacting personal information, citing CIC/TEST/A/2024/000001.",
                        "draft_response_hint": "State that file notings are reviewable and apply Section 10 severance for personal information.",
                        "exemption_risks": [
                            {
                                "section": "8(1)(j)",
                                "risk_level": "MEDIUM",
                                "reasoning": "Personal details in file notings may require redaction.",
                                "cic_precedent": "CIC/TEST/A/2024/000001",
                            }
                        ],
                    }
                )
            }
        }


class TestRTIAnalysisEngine(unittest.TestCase):
    def test_sample_rti_text_output_structure(self):
        engine = RTIAnalysisEngine(
            retriever=FakeRetriever(),
            qwen_client=FakeQwenClient(),
            department_classifier=lambda text: {"department_name": "Revenue Department"},
        )
        result = engine.analyze(
            rti_text="Please provide file notings and note sheets. If denied under Section 8(1)(j), provide reasons.",
            analysis_type="exemption_check",
        )

        self.assertEqual(result.department, "Revenue Department")
        self.assertEqual(result.analysis_type, "exemption_check")
        self.assertIn("8(1)(j)", result.detected_sections)
        self.assertTrue(result.similar_cases)
        self.assertTrue(result.exemption_risks)
        self.assertIn("CIC/TEST/A/2024/000001", result.sources_cited)
        self.assertGreater(result.recommendation_confidence, 0.0)
        self.assertLess(result.processing_time_seconds, 120.0)


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestRTIAnalysisEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RTI retrieval + Qwen legal analysis.")
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
