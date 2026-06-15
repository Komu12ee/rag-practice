"""
Hybrid retrieval over BM25 + vector search using Reciprocal Rank Fusion.

No LLM calls are made in this module.

Install requirements for full runtime:
    pip install rank_bm25 chromadb sentence-transformers tqdm pydantic

Run embedded tests:
    python src/retrieval/hybrid_retriever.py --test
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from retrieval.bm25_index import BM25Index, BM25Result
from retrieval.embedding_store import EmbeddingStore, SearchResult


RRF_K = 60
DEFAULT_POOL_SIZE = 50


class RetrievedChunk(BaseModel):
    """Final unified retrieval result."""

    chunk_id: str
    case_number: str
    source: str
    chunk_type: str
    text: str
    decision_date: Optional[str] = None
    outcome: Optional[str] = None
    department: Optional[str] = None
    public_authority: Optional[str] = None
    hearing_date: Optional[str] = None
    commissioner: Optional[str] = None
    reasoning_pattern: Optional[str] = None
    pio_learning_signal: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    bm25_score: Optional[float] = None
    vector_score: Optional[float] = None
    rrf_score: float = Field(ge=0.0)
    rank: int = Field(ge=1)


def reciprocal_rank_fusion(
    bm25_results: list[BM25Result],
    vector_results: list[SearchResult],
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """
    Merge ranked BM25 and vector results by chunk_id using RRF.

    Formula:
        score = 1 / (k + bm25_rank) + 1 / (k + vector_rank)

    Missing ranks contribute 0. Scores are normalized by the maximum RRF score.
    """
    merged: dict[str, dict[str, Any]] = {}

    for rank, item in enumerate(bm25_results, start=1):
        merged[item.chunk_id] = {
            "chunk_id": item.chunk_id,
            "case_number": item.case_number,
            "chunk_type": item.chunk_type,
            "text": item.text,
            "metadata": dict(item.metadata or {}),
            "bm25_score": item.score,
            "vector_score": None,
            "bm25_rank": rank,
            "vector_rank": None,
            "rrf_score": 1.0 / (k + rank),
        }

    for rank, item in enumerate(vector_results, start=1):
        if item.chunk_id not in merged:
            merged[item.chunk_id] = {
                "chunk_id": item.chunk_id,
                "case_number": item.case_number,
                "chunk_type": item.chunk_type,
                "text": item.text,
                "metadata": dict(item.metadata or {}),
                "bm25_score": None,
                "vector_score": item.score,
                "bm25_rank": None,
                "vector_rank": rank,
                "rrf_score": 0.0,
            }
        else:
            merged[item.chunk_id]["vector_score"] = item.score
            merged[item.chunk_id]["vector_rank"] = rank
            # Prefer richer metadata/text if BM25 metadata is sparse.
            merged[item.chunk_id]["metadata"] = {
                **dict(item.metadata or {}),
                **dict(merged[item.chunk_id].get("metadata") or {}),
            }
            if not merged[item.chunk_id].get("text"):
                merged[item.chunk_id]["text"] = item.text

        merged[item.chunk_id]["rrf_score"] += 1.0 / (k + rank)

    if not merged:
        return []

    max_score = max(item["rrf_score"] for item in merged.values()) or 1.0
    ranked = sorted(
        merged.values(),
        key=lambda item: item["rrf_score"],
        reverse=True,
    )
    for item in ranked:
        item["rrf_score"] = item["rrf_score"] / max_score
    return ranked


class HybridRetriever:
    """Unified BM25/vector retriever with graceful fallback."""

    def __init__(
        self,
        bm25_index: Optional[BM25Index] = None,
        embedding_store: Optional[EmbeddingStore] = None,
        rrf_k: int = RRF_K,
        pool_size: int = DEFAULT_POOL_SIZE,
    ):
        self.bm25_index = bm25_index if bm25_index is not None else BM25Index()
        self.embedding_store = embedding_store if embedding_store is not None else EmbeddingStore()
        self.rrf_k = rrf_k
        self.pool_size = pool_size

    def search(
        self,
        query: str,
        n_results: int = 10,
        filters: Optional[dict[str, Any]] = None,
        search_mode: str = "hybrid",
    ) -> list[RetrievedChunk]:
        """Search using bm25, vector, hybrid, or special search modes."""
        query = (query or "").strip()
        if not query:
            return []

        mode = (search_mode or "hybrid").strip().lower()
        effective_filters = self._filters_for_mode(mode, filters)

        if mode == "bm25":
            return self._bm25_only(query, n_results, effective_filters)
        if mode == "vector":
            return self._vector_only(query, n_results, effective_filters)

        # Special modes use the same hybrid merge but add metadata filters.
        return self._hybrid(query, n_results, effective_filters)

    def _hybrid(
        self,
        query: str,
        n_results: int,
        filters: Optional[dict[str, Any]],
    ) -> list[RetrievedChunk]:
        bm25_results: list[BM25Result] = []
        vector_results: list[SearchResult] = []

        try:
            bm25_results = self.bm25_index.search(query, n_results=self.pool_size)
        except Exception:
            bm25_results = []

        try:
            vector_results = self.embedding_store.search(query, n_results=self.pool_size)
        except Exception:
            vector_results = []

        if not bm25_results and vector_results:
            return self._vector_results_to_chunks(vector_results, filters, n_results)
        if not vector_results and bm25_results:
            return self._bm25_results_to_chunks(bm25_results, filters, n_results)

        fused = reciprocal_rank_fusion(bm25_results, vector_results, self.rrf_k)
        filtered = [item for item in fused if self._matches_filters(item, filters)]

        chunks: list[RetrievedChunk] = []
        for rank, item in enumerate(filtered[:n_results], start=1):
            chunks.append(self._fused_item_to_chunk(item, rank))
        return chunks

    def _bm25_only(
        self,
        query: str,
        n_results: int,
        filters: Optional[dict[str, Any]],
    ) -> list[RetrievedChunk]:
        try:
            results = self.bm25_index.search(query, n_results=self.pool_size)
        except Exception:
            return self._vector_only(query, n_results, filters)
        return self._bm25_results_to_chunks(results, filters, n_results)

    def _vector_only(
        self,
        query: str,
        n_results: int,
        filters: Optional[dict[str, Any]],
    ) -> list[RetrievedChunk]:
        try:
            results = self.embedding_store.search(query, n_results=self.pool_size)
        except Exception:
            return self._bm25_only_no_fallback(query, n_results, filters)
        return self._vector_results_to_chunks(results, filters, n_results)

    def _bm25_only_no_fallback(
        self,
        query: str,
        n_results: int,
        filters: Optional[dict[str, Any]],
    ) -> list[RetrievedChunk]:
        try:
            results = self.bm25_index.search(query, n_results=self.pool_size)
        except Exception:
            return []
        return self._bm25_results_to_chunks(results, filters, n_results)

    def _bm25_results_to_chunks(
        self,
        results: list[BM25Result],
        filters: Optional[dict[str, Any]],
        n_results: int,
    ) -> list[RetrievedChunk]:
        filtered = [item for item in results if self._matches_filters(self._single_result_item(item), filters)]
        max_score = max((item.score for item in filtered), default=1.0) or 1.0
        chunks: list[RetrievedChunk] = []
        for rank, item in enumerate(filtered[:n_results], start=1):
            metadata = dict(item.metadata or {})
            chunks.append(
                RetrievedChunk(
                    chunk_id=item.chunk_id,
                    case_number=item.case_number,
                    source=str(metadata.get("source") or metadata.get("source_type") or ""),
                    chunk_type=item.chunk_type,
                    text=item.text,
                    decision_date=self._empty_to_none(metadata.get("decision_date") or metadata.get("date")),
                    outcome=self._empty_to_none(metadata.get("outcome")),
                    department=self._empty_to_none(metadata.get("department") or metadata.get("public_authority")),
                    public_authority=self._empty_to_none(metadata.get("public_authority")),
                    hearing_date=self._empty_to_none(metadata.get("hearing_date")),
                    commissioner=self._empty_to_none(metadata.get("commissioner")),
                    reasoning_pattern=self._empty_to_none(metadata.get("reasoning_pattern")),
                    pio_learning_signal=self._empty_to_none(metadata.get("pio_learning_signal")),
                    metadata=metadata,
                    bm25_score=item.score,
                    vector_score=None,
                    rrf_score=max(0.0, float(item.score) / max_score),
                    rank=rank,
                )
            )
        return chunks

    def _vector_results_to_chunks(
        self,
        results: list[SearchResult],
        filters: Optional[dict[str, Any]],
        n_results: int,
    ) -> list[RetrievedChunk]:
        filtered = [item for item in results if self._matches_filters(self._single_result_item(item), filters)]
        max_score = max((item.score for item in filtered), default=1.0) or 1.0
        chunks: list[RetrievedChunk] = []
        for rank, item in enumerate(filtered[:n_results], start=1):
            metadata = dict(item.metadata or {})
            chunks.append(
                RetrievedChunk(
                    chunk_id=item.chunk_id,
                    case_number=item.case_number,
                    source=str(metadata.get("source") or metadata.get("source_type") or ""),
                    chunk_type=item.chunk_type,
                    text=item.text,
                    decision_date=self._empty_to_none(metadata.get("decision_date") or metadata.get("date")),
                    outcome=self._empty_to_none(metadata.get("outcome")),
                    department=self._empty_to_none(metadata.get("department") or metadata.get("public_authority")),
                    public_authority=self._empty_to_none(metadata.get("public_authority")),
                    hearing_date=self._empty_to_none(metadata.get("hearing_date")),
                    commissioner=self._empty_to_none(metadata.get("commissioner")),
                    reasoning_pattern=self._empty_to_none(metadata.get("reasoning_pattern")),
                    pio_learning_signal=self._empty_to_none(metadata.get("pio_learning_signal")),
                    metadata=metadata,
                    bm25_score=None,
                    vector_score=item.score,
                    rrf_score=max(0.0, float(item.score) / max_score),
                    rank=rank,
                )
            )
        return chunks

    def _fused_item_to_chunk(self, item: dict[str, Any], rank: int) -> RetrievedChunk:
        metadata = dict(item.get("metadata") or {})
        return RetrievedChunk(
            chunk_id=str(item.get("chunk_id", "")),
            case_number=str(item.get("case_number") or metadata.get("case_number", "")),
            source=str(metadata.get("source") or metadata.get("source_type") or ""),
            chunk_type=str(item.get("chunk_type") or metadata.get("chunk_type", "")),
            text=str(item.get("text", "")),
            decision_date=self._empty_to_none(metadata.get("decision_date") or metadata.get("date")),
            outcome=self._empty_to_none(metadata.get("outcome")),
            department=self._empty_to_none(metadata.get("department") or metadata.get("public_authority")),
            public_authority=self._empty_to_none(metadata.get("public_authority")),
            hearing_date=self._empty_to_none(metadata.get("hearing_date")),
            commissioner=self._empty_to_none(metadata.get("commissioner")),
            reasoning_pattern=self._empty_to_none(metadata.get("reasoning_pattern")),
            pio_learning_signal=self._empty_to_none(metadata.get("pio_learning_signal")),
            metadata=metadata,
            bm25_score=item.get("bm25_score"),
            vector_score=item.get("vector_score"),
            rrf_score=float(item.get("rrf_score", 0.0)),
            rank=rank,
        )

    @staticmethod
    def _filters_for_mode(mode: str, filters: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        effective = dict(filters or {})
        if mode == "commission_findings":
            effective["chunk_type"] = "COMMISSION_FINDINGS"
        elif mode == "circulars":
            effective["source"] = "CIRCULAR"
        elif mode == "similar_case":
            # The query may be full case text; no additional hard filter is needed.
            pass
        return effective or None

    @staticmethod
    def _matches_filters(item: dict[str, Any], filters: Optional[dict[str, Any]]) -> bool:
        if not filters:
            return True
        metadata = dict(item.get("metadata") or {})
        for key, expected in filters.items():
            if expected is None or expected == "":
                continue
            expected_text = str(expected).lower()
            if key == "year":
                decision_date = str(metadata.get("decision_date", ""))
                if not decision_date.startswith(str(expected)):
                    return False
                continue
            actual = metadata.get(key, item.get(key, ""))
            if str(actual).lower() != expected_text:
                return False
        return True

    @staticmethod
    def _single_result_item(item: BM25Result | SearchResult) -> dict[str, Any]:
        return {
            "chunk_id": item.chunk_id,
            "case_number": item.case_number,
            "chunk_type": item.chunk_type,
            "text": item.text,
            "metadata": dict(item.metadata or {}),
        }

    @staticmethod
    def _empty_to_none(value: Any) -> Optional[str]:
        text = "" if value is None else str(value)
        return text or None


class FakeBM25:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def search(self, query: str, n_results: int = 20, filters: Optional[dict[str, Any]] = None):
        if self.fail:
            raise RuntimeError("BM25 unavailable")
        return [
            BM25Result(
                chunk_id="a",
                case_number="CIC/1",
                chunk_type="COMMISSION_FINDINGS",
                text="section 8(1)(j) file noting disclosure",
                score=10.0,
                metadata={
                    "source": "CIC",
                    "chunk_type": "COMMISSION_FINDINGS",
                    "decision_date": "2024-01-01",
                    "outcome": "PARTIAL",
                    "department": "Revenue",
                },
            ),
            BM25Result(
                chunk_id="b",
                case_number="CIC/2",
                chunk_type="DIRECTIONS",
                text="file noting directions",
                score=8.0,
                metadata={
                    "source": "CIC",
                    "chunk_type": "DIRECTIONS",
                    "decision_date": "2024-02-01",
                    "outcome": "APPEAL_ALLOWED",
                    "department": "Finance",
                },
            ),
        ][:n_results]


class FakeVector:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def search(self, query: str, n_results: int = 10, filters: Optional[dict[str, Any]] = None):
        if self.fail:
            raise RuntimeError("Vector unavailable")
        return [
            SearchResult(
                chunk_id="b",
                case_number="CIC/2",
                chunk_type="DIRECTIONS",
                text="file noting directions",
                score=0.95,
                metadata={
                    "source": "CIC",
                    "chunk_type": "DIRECTIONS",
                    "decision_date": "2024-02-01",
                    "outcome": "APPEAL_ALLOWED",
                    "department": "Finance",
                },
            ),
            SearchResult(
                chunk_id="a",
                case_number="CIC/1",
                chunk_type="COMMISSION_FINDINGS",
                text="section 8(1)(j) file noting disclosure",
                score=0.90,
                metadata={
                    "source": "CIC",
                    "chunk_type": "COMMISSION_FINDINGS",
                    "decision_date": "2024-01-01",
                    "outcome": "PARTIAL",
                    "department": "Revenue",
                },
            ),
        ][:n_results]


class TestHybridRetriever(unittest.TestCase):
    def test_rrf_hybrid_beats_single_mode_overlap(self):
        retriever = HybridRetriever(bm25_index=FakeBM25(), embedding_store=FakeVector())
        hybrid = retriever.search("section 8(1)(j) file noting", search_mode="hybrid", n_results=2)
        bm25 = retriever.search("section 8(1)(j) file noting", search_mode="bm25", n_results=2)
        vector = retriever.search("section 8(1)(j) file noting", search_mode="vector", n_results=2)

        self.assertEqual(len(hybrid), 2)
        self.assertGreaterEqual(hybrid[0].rrf_score, bm25[0].rrf_score)
        self.assertGreaterEqual(hybrid[0].rrf_score, vector[0].rrf_score)
        self.assertIsNotNone(hybrid[0].bm25_score)
        self.assertIsNotNone(hybrid[0].vector_score)

    def test_filters_and_special_mode(self):
        retriever = HybridRetriever(bm25_index=FakeBM25(), embedding_store=FakeVector())
        results = retriever.search(
            "section 8(1)(j) file noting",
            search_mode="commission_findings",
            n_results=5,
        )
        self.assertTrue(results)
        self.assertTrue(all(item.chunk_type == "COMMISSION_FINDINGS" for item in results))

        filtered = retriever.search(
            "file noting",
            filters={"department": "Finance", "year": "2024"},
            n_results=5,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].department, "Finance")

    def test_fallbacks(self):
        vector_only = HybridRetriever(bm25_index=FakeBM25(fail=True), embedding_store=FakeVector())
        self.assertTrue(vector_only.search("file noting", search_mode="hybrid"))

        bm25_only = HybridRetriever(bm25_index=FakeBM25(), embedding_store=FakeVector(fail=True))
        self.assertTrue(bm25_only.search("file noting", search_mode="hybrid"))


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestHybridRetriever)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid BM25 + vector retrieval over legal chunks.")
    parser.add_argument("--test", action="store_true", help="Run embedded unit tests.")
    parser.add_argument("--query", help="Search query.")
    parser.add_argument("--mode", default="hybrid", help="bm25, vector, hybrid, commission_findings, circulars, similar_case.")
    parser.add_argument("--n-results", type=int, default=10)
    parser.add_argument("--filter", action="append", default=[], help="Metadata filter key=value. Repeatable.")
    return parser.parse_args()


def _parse_filters(raw_filters: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for item in raw_filters:
        if "=" not in item:
            raise ValueError(f"Invalid filter '{item}'. Use key=value.")
        key, value = item.split("=", 1)
        filters[key.strip()] = value.strip()
    return filters


def main() -> int:
    args = parse_args()
    if args.test:
        return _run_tests()
    if args.query:
        retriever = HybridRetriever()
        results = retriever.search(
            args.query,
            n_results=args.n_results,
            filters=_parse_filters(args.filter),
            search_mode=args.mode,
        )
        for result in results:
            print(result.model_dump_json())
        return 0

    print("No action requested. Use --query or --test.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
