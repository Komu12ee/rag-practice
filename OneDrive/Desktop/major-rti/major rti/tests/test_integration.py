"""
End-to-end integration tests for MAM-RTI Phase 1.

These tests use real CIC decision PDFs. By default they look for:
    data/cic_decisions/

If this checkout stores CIC decisions under a different directory, set:
    $env:CIC_DECISIONS_DIR = "data/cic_pdfs_past_cases"

Fast CPU-only usage:
    pytest tests/test_integration.py -v --no-llm
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from engine.rti_analysis_engine import RTIAnalysisEngine
from generation.response_templates import ResponseGenerator, RESPONSE_TYPES
from pipeline.batch_extractor import process_pdf, safe_case_id
from pipeline.legal_chunker import LegalChunk, LegalChunker
from pipeline.legal_extractor import LegalExtractor
from pipeline.legal_segmenter import LegalSegmenter, SegmentedDecision
from rag.context_assembler import ContextAssembler
from retrieval.bm25_index import BM25Index
from retrieval.hybrid_retriever import HybridRetriever, RetrievedChunk
from storage.metadata_store import MetadataStore


REPORT_LINES: list[str] = []
REPORT_PATH = PROJECT_ROOT / "data" / "logs" / "test_report.txt"
QUERY = "file noting exemption section 8(1)(j)"
SAMPLE_SIZE = 5
SCAN_LIMIT = int(os.getenv("CIC_SAMPLE_SCAN_LIMIT", "80"))


@dataclass
class ProcessedDecision:
    pdf_path: Path
    text_path: Path
    text: str
    segmented: SegmentedDecision
    extracted_case: Any
    chunks: list[LegalChunk]


class NullVectorStore:
    """Force HybridRetriever to exercise real BM25 fallback without model downloads."""

    def search(self, query: str, n_results: int = 10, filters: dict[str, Any] | None = None):
        raise RuntimeError("Vector search disabled for CPU-only integration test.")


class NoLLMClient:
    """Deterministic Qwen replacement used only when pytest is run with --no-llm."""

    def chat(self, model: str, messages: list[dict[str, str]], format: str, options: dict[str, Any]):
        prompt = messages[0]["content"]
        case_numbers = re.findall(r"\b(?:CIC|SIC)/[A-Z0-9/_-]+\b", prompt)
        precedent = case_numbers[0] if case_numbers else ""
        content = {
            "recommendation": (
                f"Review disclosure of file notings with redaction of personal information. "
                f"Use retrieved CIC precedent {precedent}."
            ),
            "draft_response_hint": (
                "Provide disclosable file notings and apply Section 10 severance for personal details."
            ),
            "exemption_risks": [],
        }
        if precedent:
            content["exemption_risks"].append(
                {
                    "section": "8(1)(j)",
                    "risk_level": "MEDIUM",
                    "reasoning": "Personal information in file notings may need redaction.",
                    "cic_precedent": precedent,
                }
            )
        return {"message": {"content": json.dumps(content)}}


def _record(test_name: str, status: str, details: str) -> None:
    line = f"{test_name}: {status} | {details}"
    REPORT_LINES.append(line)
    print(line)


@pytest.fixture(scope="session", autouse=True)
def write_test_report():
    REPORT_LINES.clear()
    yield
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(REPORT_LINES) + "\n", encoding="utf-8")


@pytest.fixture(scope="session")
def no_llm(pytestconfig) -> bool:
    return bool(pytestconfig.getoption("--no-llm"))


@pytest.fixture(scope="session")
def cic_pdf_dir() -> Path:
    configured = os.getenv("CIC_DECISIONS_DIR")
    preferred = PROJECT_ROOT / "data" / "cic_decisions"
    fallback = PROJECT_ROOT / "data" / "cic_pdfs_past_cases"

    if configured:
        path = (PROJECT_ROOT / configured).resolve() if not Path(configured).is_absolute() else Path(configured)
    elif preferred.exists():
        path = preferred
    else:
        path = fallback
        _record(
            "Fixture: CIC PDF directory",
            "WARN",
            f"data/cic_decisions not found; using real CIC PDFs from {fallback}",
        )

    assert path.exists(), (
        f"Required CIC PDF folder not found. Expected {preferred}, or set CIC_DECISIONS_DIR "
        f"to a folder with at least {SAMPLE_SIZE} real CIC PDFs."
    )
    assert path.is_dir(), f"CIC_DECISIONS_DIR is not a directory: {path}"
    return path


@pytest.fixture(scope="session")
def processed_corpus(tmp_path_factory, cic_pdf_dir: Path, no_llm: bool):
    pytest.importorskip("fitz", reason="PyMuPDF is required for real PDF extraction.")
    pytest.importorskip("rank_bm25", reason="rank_bm25 is required for real BM25 retrieval.")

    tmp_root = tmp_path_factory.mktemp("mam_rti_integration")
    extracted_dir = tmp_root / "extracted"
    metadata_root = tmp_root / "metadata"
    chunks_root = tmp_root / "chunks"
    db_path = tmp_root / "cases.db"
    bm25_path = tmp_root / "bm25_index.pkl"
    docmap_path = tmp_root / "bm25_docmap.json"

    segmenter = LegalSegmenter()
    extractor = LegalExtractor()
    store = MetadataStore(db_path=db_path, metadata_root=metadata_root, export_path=tmp_root / "all_cases.jsonl")
    chunker = LegalChunker(chunks_root=chunks_root)

    pdfs = sorted(cic_pdf_dir.rglob("*.pdf"))
    assert len(pdfs) >= SAMPLE_SIZE, f"Need at least {SAMPLE_SIZE} real CIC PDFs in {cic_pdf_dir}; found {len(pdfs)}."

    candidates: list[ProcessedDecision] = []
    errors: list[str] = []

    for pdf_path in pdfs[:SCAN_LIMIT]:
        try:
            status = process_pdf(pdf_path, cic_pdf_dir, extracted_dir)
            case_id = safe_case_id(pdf_path, cic_pdf_dir)
            text_path = extracted_dir / f"{case_id}.txt"
            if not text_path.exists():
                errors.append(f"{pdf_path.name}: extraction status={status}, text file missing")
                continue

            text = text_path.read_text(encoding="utf-8", errors="replace")
            if len(text.strip()) < 500:
                errors.append(f"{pdf_path.name}: extracted text too short ({len(text.strip())} chars)")
                continue

            segmented = segmenter.segment(text)
            extracted_case = extractor.extract(segmented, use_llm=not no_llm, source_file=str(text_path))
            chunks = chunker.chunk(segmented, extracted_case, save=True)
            store.save(extracted_case)

            candidates.append(
                ProcessedDecision(
                    pdf_path=pdf_path,
                    text_path=text_path,
                    text=text,
                    segmented=segmented,
                    extracted_case=extracted_case,
                    chunks=chunks,
                )
            )
        except Exception as exc:
            errors.append(f"{pdf_path.name}: {type(exc).__name__}: {exc}")

        if len(candidates) >= max(SAMPLE_SIZE, 8) and _has_8_1_j_candidate(candidates):
            break

    assert len(candidates) >= SAMPLE_SIZE, (
        f"Could not process {SAMPLE_SIZE} real CIC PDFs from {cic_pdf_dir}. "
        f"Processed={len(candidates)}. Recent errors={errors[-5:]}"
    )

    selected = _select_representative_decisions(candidates, SAMPLE_SIZE)
    selected_case_numbers = {item.extracted_case.case_number for item in selected}

    # Remove non-selected chunk files so retrieval relevance is evaluated on the same selected corpus.
    for jsonl_file in chunks_root.rglob("*.jsonl"):
        if not any(_safe_case_filename(case_number) in jsonl_file.name for case_number in selected_case_numbers):
            jsonl_file.unlink()

    bm25 = BM25Index(index_path=bm25_path, docmap_path=docmap_path)
    bm25.build(chunks_root)
    bm25.save(bm25_path)
    retriever = HybridRetriever(bm25_index=bm25, embedding_store=NullVectorStore())

    _record(
        "Fixture: processed corpus",
        "PASS",
        f"processed={len(selected)} pdfs, chunks={sum(len(item.chunks) for item in selected)}, no_llm={no_llm}",
    )

    return {
        "decisions": selected,
        "chunks_root": chunks_root,
        "metadata_store": store,
        "bm25": bm25,
        "retriever": retriever,
        "no_llm": no_llm,
    }


@pytest.fixture(scope="session")
def retrieved_chunks(processed_corpus) -> list[RetrievedChunk]:
    retriever: HybridRetriever = processed_corpus["retriever"]
    results = retriever.search(QUERY, n_results=10, search_mode="hybrid")
    return results


def test_1_extraction_quality(processed_corpus):
    decisions: list[ProcessedDecision] = processed_corpus["decisions"]
    case_numbers = [d.extracted_case.case_number for d in decisions if d.extracted_case.case_number != "UNKNOWN"]
    sections = [d.extracted_case.sections_invoked for d in decisions if d.extracted_case.sections_invoked]
    outcomes = [d.extracted_case.outcome for d in decisions if d.extracted_case.outcome]

    _record(
        "Test 1: Extraction Quality",
        "PASS" if len(case_numbers) >= 4 and len(sections) >= 4 and len(outcomes) >= 3 else "FAIL",
        f"case_numbers={len(case_numbers)}/5 sections={len(sections)}/5 outcomes={len(outcomes)}/5",
    )

    assert len(case_numbers) >= 4, f"Expected case_number for 4+ of 5 PDFs, got {len(case_numbers)}: {case_numbers}"
    assert len(sections) >= 4, f"Expected sections_invoked for 4+ of 5 PDFs, got {len(sections)}."
    assert len(outcomes) >= 3, f"Expected outcome for 3+ of 5 PDFs, got {len(outcomes)}: {outcomes}"


def test_2_segmentation_coverage(processed_corpus):
    decisions: list[ProcessedDecision] = processed_corpus["decisions"]
    findings = [d for d in decisions if d.segmented.COMMISSION_FINDINGS.strip()]
    directions = [d for d in decisions if d.segmented.DIRECTIONS.strip()]

    _record(
        "Test 2: Segmentation Coverage",
        "PASS" if len(findings) >= 4 and len(directions) >= 3 else "FAIL",
        f"commission_findings={len(findings)}/5 directions={len(directions)}/5",
    )

    assert len(findings) >= 4, f"Expected COMMISSION_FINDINGS for 4+ of 5 decisions, got {len(findings)}."
    assert len(directions) >= 3, f"Expected DIRECTIONS for 3+ of 5 decisions, got {len(directions)}."


def test_3_retrieval_relevance(retrieved_chunks: list[RetrievedChunk]):
    has_findings = any(result.chunk_type == "COMMISSION_FINDINGS" for result in retrieved_chunks)
    has_8_1_j = any(_result_has_section(result, "8(1)(j)") for result in retrieved_chunks)

    _record(
        "Test 3: Retrieval Relevance",
        "PASS" if len(retrieved_chunks) >= 3 and has_findings and has_8_1_j else "FAIL",
        f"results={len(retrieved_chunks)} has_findings={has_findings} has_8_1_j={has_8_1_j}",
    )

    assert len(retrieved_chunks) >= 3, f"Expected at least 3 retrieval results, got {len(retrieved_chunks)}."
    assert has_findings, "Expected at least 1 retrieval result with chunk_type=COMMISSION_FINDINGS."
    assert has_8_1_j, "Expected at least 1 retrieval result with sections_invoked containing 8(1)(j)."


def test_4_context_assembly(retrieved_chunks: list[RetrievedChunk]):
    chunks = retrieved_chunks[:5]
    assert chunks, "Need retrieved chunks for context assembly test."
    assembled = ContextAssembler().assemble(
        query=QUERY,
        retrieved_chunks=chunks,
        query_type="exemption_check",
    )
    sources_match = all(source in assembled.context_block for source in assembled.sources_used)

    _record(
        "Test 4: Context Assembly",
        "PASS" if assembled.token_estimate < 6500 and sources_match else "FAIL",
        f"token_estimate={assembled.token_estimate} sources_used={assembled.sources_used}",
    )

    assert assembled.token_estimate < 6500, f"Expected token_estimate < 6500, got {assembled.token_estimate}."
    assert sources_match, f"sources_used must appear in context_block: {assembled.sources_used}"


def test_5_full_pipeline(processed_corpus):
    retriever: HybridRetriever = processed_corpus["retriever"]
    qwen_client = NoLLMClient() if processed_corpus["no_llm"] else None
    engine = RTIAnalysisEngine(
        retriever=retriever,
        qwen_client=qwen_client,
        department_classifier=lambda text: {"department_name": "Test Department"},
    )
    analysis = engine.analyze(
        rti_text=(
            "Please provide file notings, note sheets, and correspondence on the decision. "
            "If any information is denied under Section 8(1)(j), please provide reasons."
        ),
        analysis_type="exemption_check",
        department_hint="Test Department",
    )
    responses = ResponseGenerator().generate_all(
        analysis=analysis,
        appellant_name="Test Applicant",
        rti_date="2026-06-01",
        rti_subject="file noting access",
        reply_date="15/06/2026",
    )

    citation_present = any(source in responses.draft_rti_reply for source in analysis.sources_cited)
    response_type = responses.pio_recommendation.recommended_response_type

    _record(
        "Test 5: Full Pipeline",
        "PASS" if analysis.similar_cases and analysis.sources_cited and citation_present and response_type in RESPONSE_TYPES else "FAIL",
        (
            f"similar_cases={len(analysis.similar_cases)} sources={analysis.sources_cited} "
            f"response_type={response_type} elapsed={analysis.processing_time_seconds}s"
        ),
    )

    assert analysis.similar_cases, "Expected RTIAnalysisResult.similar_cases to be non-empty."
    assert analysis.sources_cited, "Expected RTIAnalysisResult.sources_cited to contain real retrieved case numbers."
    assert citation_present, "DraftRTIReply must contain at least one citation from sources_cited."
    assert response_type in RESPONSE_TYPES, f"Invalid recommendation enum: {response_type}"
    assert analysis.processing_time_seconds < 120, f"Query analysis exceeded 120s: {analysis.processing_time_seconds}s"


def _select_representative_decisions(candidates: list[ProcessedDecision], sample_size: int) -> list[ProcessedDecision]:
    scored = sorted(candidates, key=_decision_score, reverse=True)
    selected = scored[:sample_size]
    if not any(_decision_has_8_1_j(item) for item in selected):
        for candidate in scored[sample_size:]:
            if _decision_has_8_1_j(candidate):
                selected[-1] = candidate
                break
    return selected


def _decision_score(decision: ProcessedDecision) -> int:
    score = 0
    if decision.extracted_case.case_number != "UNKNOWN":
        score += 4
    if decision.extracted_case.sections_invoked:
        score += 3
    if decision.extracted_case.outcome:
        score += 2
    if decision.segmented.COMMISSION_FINDINGS.strip():
        score += 2
    if decision.segmented.DIRECTIONS.strip():
        score += 2
    if _decision_has_8_1_j(decision):
        score += 5
    if re.search(r"(?i)\bfile\s+not(?:ing|ings|e|es)?\b|\bnote\s+sheet\b", decision.text):
        score += 3
    return score


def _has_8_1_j_candidate(candidates: list[ProcessedDecision]) -> bool:
    return any(_decision_has_8_1_j(candidate) for candidate in candidates)


def _decision_has_8_1_j(decision: ProcessedDecision) -> bool:
    if any(_normalize_section(section) == "8(1)(j)" for section in decision.extracted_case.sections_invoked):
        return True
    return "8(1)(j)" in decision.text.replace(" ", "").lower()


def _result_has_section(result: RetrievedChunk, section: str) -> bool:
    expected = _normalize_section(section)
    metadata = getattr(result, "metadata", {}) or {}
    sections = metadata.get("sections_invoked") or []
    if isinstance(sections, str):
        sections = [sections]
    if any(_normalize_section(item) == expected for item in sections):
        return True
    return expected in result.text.replace(" ", "").lower()


def _normalize_section(section: str) -> str:
    return re.sub(r"\s+", "", str(section or "").lower().replace("section", ""))


def _safe_case_filename(case_number: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(case_number or "")).strip("._-") or "UNKNOWN"
