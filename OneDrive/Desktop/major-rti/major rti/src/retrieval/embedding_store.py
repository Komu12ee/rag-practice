"""
Local ChromaDB embedding store for legal chunks.

Embeds LegalChunk objects with sentence-transformers/all-MiniLM-L6-v2 and
stores them in a persistent local ChromaDB collection.

Install requirements:
    pip install chromadb sentence-transformers tqdm pydantic

Run embedded tests:
    python src/retrieval/embedding_store.py --test
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pipeline.legal_chunker import LegalChunk


DEFAULT_PERSIST_DIR = PROJECT_ROOT / "data" / "vectorstore" / "legal_chunks"
DEFAULT_COLLECTION_NAME = "legal_chunks"
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MULTILINGUAL_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BATCH_SIZE = 32


class SearchResult(BaseModel):
    """One semantic retrieval hit."""

    chunk_id: str
    case_number: str
    chunk_type: str
    text: str
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingStore:
    """Persistent local ChromaDB store for LegalChunk embeddings."""

    def __init__(
        self,
        persist_dir: str | Path = DEFAULT_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        model_name: str = DEFAULT_MODEL_NAME,
        batch_size: int = BATCH_SIZE,
    ):
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None
        self._client = None
        self._collection = None

    def embed_and_store(self, chunks: list[LegalChunk]) -> int:
        """Embed and store chunks, skipping already embedded chunk IDs."""
        if not chunks:
            return 0

        from tqdm import tqdm

        collection = self._get_collection()
        pending = [chunk for chunk in chunks if not self.check_exists(chunk.chunk_id)]
        stored_count = 0

        for batch in tqdm(
            self._batches(pending, self.batch_size),
            total=(len(pending) + self.batch_size - 1) // self.batch_size,
            desc="Embedding legal chunks",
            unit="batch",
        ):
            texts = [chunk.text for chunk in batch]
            embeddings = self._embed_texts(texts)
            collection.add(
                ids=[chunk.chunk_id for chunk in batch],
                documents=texts,
                embeddings=embeddings,
                metadatas=[self._metadata_for_chunk(chunk) for chunk in batch],
            )
            stored_count += len(batch)

        return stored_count

    def search(
        self,
        query: str,
        n_results: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        """Run semantic similarity search with optional metadata filters."""
        query = (query or "").strip()
        if not query:
            return []

        collection = self._get_collection()
        query_embedding = self._embed_texts([query])[0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=self._normalize_filters(filters),
            include=["documents", "metadatas", "distances"],
        )
        return self._to_search_results(result)

    def search_by_chunk_type(
        self,
        query: str,
        chunk_type: str,
        n_results: int = 5,
    ) -> list[SearchResult]:
        """Search only within one legal chunk type."""
        return self.search(query, n_results=n_results, filters={"chunk_type": chunk_type})

    def get_collection_stats(self) -> dict[str, Any]:
        """Return total chunks and counts by source/chunk_type."""
        collection = self._get_collection()
        total = collection.count()
        if total == 0:
            return {"total_chunks": 0, "by_source": {}, "by_chunk_type": {}}

        records = collection.get(include=["metadatas"], limit=total)
        metadatas = records.get("metadatas") or []
        by_source = Counter(str(meta.get("source", "UNKNOWN")) for meta in metadatas)
        by_chunk_type = Counter(str(meta.get("chunk_type", "UNKNOWN")) for meta in metadatas)

        return {
            "total_chunks": total,
            "by_source": dict(sorted(by_source.items())),
            "by_chunk_type": dict(sorted(by_chunk_type.items())),
        }

    def check_exists(self, chunk_id: str) -> bool:
        """Return True when chunk_id is already stored."""
        if not chunk_id:
            return False
        collection = self._get_collection()
        result = collection.get(ids=[chunk_id], include=[])
        return bool(result.get("ids"))

    def _get_collection(self):
        if self._collection is not None:
            return self._collection

        chromadb = self._import_chromadb()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self.model_name,
            },
        )
        return self._collection

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: sentence-transformers. "
                "Install with: pip install chromadb sentence-transformers tqdm pydantic"
            ) from exc

        # CPU is explicit so the pipeline does not require a GPU.
        self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vectors.astype("float32").tolist()

    @staticmethod
    def _import_chromadb():
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: chromadb. "
                "Install with: pip install chromadb sentence-transformers tqdm pydantic"
            ) from exc
        return chromadb

    @staticmethod
    def _batches(items: list[LegalChunk], batch_size: int):
        for index in range(0, len(items), batch_size):
            yield items[index:index + batch_size]

    @staticmethod
    def _metadata_for_chunk(chunk: LegalChunk) -> dict[str, Any]:
        """Chroma metadata values must be scalar primitives."""
        return {
            "case_number": chunk.case_number,
            "source": chunk.source,
            "chunk_type": chunk.chunk_type,
            "decision_date": chunk.decision_date or "",
            "outcome": chunk.outcome or "",
            "department": chunk.department or "",
            "commissioner": chunk.commissioner or "",
        }

    @staticmethod
    def _normalize_filters(filters: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not filters:
            return None
        clean = {
            key: value
            for key, value in filters.items()
            if value is not None and value != ""
        }
        if not clean:
            return None
        if len(clean) == 1:
            return clean
        return {"$and": [{key: value} for key, value in clean.items()]}

    @staticmethod
    def _score_from_distance(distance: float) -> float:
        # For cosine space, Chroma returns a distance where smaller is better.
        score = 1.0 - float(distance)
        return max(0.0, min(1.0, score))

    def _to_search_results(self, raw_result: dict[str, Any]) -> list[SearchResult]:
        ids = (raw_result.get("ids") or [[]])[0]
        documents = (raw_result.get("documents") or [[]])[0]
        metadatas = (raw_result.get("metadatas") or [[]])[0]
        distances = (raw_result.get("distances") or [[]])[0]

        results: list[SearchResult] = []
        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            metadata = metadata or {}
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    case_number=str(metadata.get("case_number", "")),
                    chunk_type=str(metadata.get("chunk_type", "")),
                    text=document or "",
                    score=self._score_from_distance(distance),
                    metadata=dict(metadata),
                )
            )
        return results


class TestEmbeddingStore(unittest.TestCase):
    def setUp(self) -> None:
        if not _deps_available():
            self.skipTest("chromadb and sentence-transformers are not installed")
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EmbeddingStore(
            persist_dir=Path(self.tmp.name) / "vectorstore",
            collection_name="legal_chunks_test",
            batch_size=2,
        )

    def tearDown(self) -> None:
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def _chunks(self) -> list[LegalChunk]:
        base = {
            "case_number": "CIC/TEST/A/2024/000001",
            "source": "CIC",
            "decision_date": "2024-05-01",
            "outcome": "PARTIAL",
            "department": "Department of Revenue",
            "commissioner": "Shri Example Kumar",
            "token_count": 20,
            "metadata": {},
        }
        texts = [
            ("RTI_REQUEST", "[RTI_REQUEST] Request for inspection reports and file notings."),
            ("CPIO_REPLY", "[CPIO_REPLY] CPIO denied personal information under Section 8(1)(j)."),
            ("COMMISSION_FINDINGS", "[COMMISSION_FINDINGS] Commission held that public records can be disclosed after redaction."),
            ("PUBLIC_INTEREST", "[PUBLIC_INTEREST] Larger public interest supported disclosure."),
            ("DIRECTIONS", "[DIRECTIONS] CPIO was directed to provide revised information."),
        ]
        return [
            LegalChunk(
                chunk_id=f"chunk-{index}",
                chunk_type=chunk_type,
                text=text,
                **base,
            )
            for index, (chunk_type, text) in enumerate(texts)
        ]

    def test_store_search_and_stats(self):
        stored = self.store.embed_and_store(self._chunks())
        self.assertEqual(stored, 5)
        self.assertTrue(self.store.check_exists("chunk-0"))

        duplicate_stored = self.store.embed_and_store(self._chunks())
        self.assertEqual(duplicate_stored, 0)

        results = self.store.search("public records disclosure", n_results=3)
        self.assertGreaterEqual(len(results), 1)
        self.assertIsInstance(results[0], SearchResult)

        filtered = self.store.search_by_chunk_type(
            "public records disclosure",
            "COMMISSION_FINDINGS",
            n_results=5,
        )
        self.assertTrue(all(item.chunk_type == "COMMISSION_FINDINGS" for item in filtered))

        stats = self.store.get_collection_stats()
        self.assertEqual(stats["total_chunks"], 5)
        self.assertEqual(stats["by_source"]["CIC"], 5)
        self.assertEqual(stats["by_chunk_type"]["COMMISSION_FINDINGS"], 1)


def _deps_available() -> bool:
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestEmbeddingStore)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local ChromaDB embedding store for legal chunks.")
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
