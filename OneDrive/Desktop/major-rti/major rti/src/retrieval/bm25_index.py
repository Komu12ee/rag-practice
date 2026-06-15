"""
BM25 keyword index for MAM-RTI legal chunks.

Input:
    data/chunks/**/*.jsonl files produced by src/pipeline/legal_chunker.py

Outputs:
    data/indexes/bm25_index.pkl
    data/indexes/bm25_docmap.json

Install requirements:
    pip install rank_bm25 pydantic tqdm

CLI:
    python src/retrieval/bm25_index.py --build --chunks-folder data/chunks
    python src/retrieval/bm25_index.py --search "file noting exemption 8(1)(j)"
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import string
import sys
import tempfile
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


DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "indexes" / "bm25_index.pkl"
DEFAULT_DOCMAP_PATH = PROJECT_ROOT / "data" / "indexes" / "bm25_docmap.json"
DEFAULT_CHUNKS_FOLDER = PROJECT_ROOT / "data" / "chunks"

LEGAL_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "in",
    "of",
    "and",
    "to",
    "that",
    "this",
    "it",
    "be",
    "as",
    "at",
    "by",
}

SECTION_RE = re.compile(
    r"\b\d+\s*\(\s*\d+\s*\)\s*\(\s*[a-z]\s*\)|"
    r"\b\d+\s*\(\s*\d+\s*\)|"
    r"\bsection\s+\d+\s*\(\s*\d+\s*\)\s*\(\s*[a-z]\s*\)|"
    r"\bsection\s+\d+\s*\(\s*\d+\s*\)|"
    r"\bsection\s+\d+\b",
    re.IGNORECASE,
)

CASE_RE = re.compile(r"\b(?:CIC|SIC)[/_-][A-Z0-9/_-]+\b", re.IGNORECASE)
WORD_RE = re.compile(r"[a-z0-9]+(?:/[a-z0-9]+)*")


class BM25Result(BaseModel):
    """One BM25 search result."""

    chunk_id: str
    case_number: str
    chunk_type: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


def legal_tokenize(text: str) -> list[str]:
    """
    Tokenize legal text for BM25.

    - Lowercases all text.
    - Preserves section references like 8(1)(j), 20(1), section 6(3).
    - Preserves CIC/SIC-style case-number fragments.
    - Removes punctuation from normal words.
    - Removes a small legal-safe stopword list.
    """
    text = (text or "").lower()

    special_tokens: list[str] = []

    def keep_section(match: re.Match) -> str:
        token = re.sub(r"\s+", "", match.group(0).lower())
        token = re.sub(r"^section", "", token).strip()
        if token:
            special_tokens.append(token)
        return " "

    def keep_case(match: re.Match) -> str:
        token = match.group(0).lower().replace("_", "/").replace("-", "/")
        special_tokens.append(token)
        special_tokens.extend(part for part in token.split("/") if part)
        return " "

    text = SECTION_RE.sub(keep_section, text)
    text = CASE_RE.sub(keep_case, text)

    # Remove punctuation except slash, already handled in WORD_RE.
    punctuation = string.punctuation.replace("/", "")
    text = text.translate(str.maketrans({char: " " for char in punctuation}))

    tokens = special_tokens + WORD_RE.findall(text)
    return [token for token in tokens if token and token not in LEGAL_STOPWORDS]


class BM25Index:
    """Build, save, load, and query a local BM25 index over LegalChunk JSONL."""

    def __init__(
        self,
        index_path: str | Path = DEFAULT_INDEX_PATH,
        docmap_path: str | Path = DEFAULT_DOCMAP_PATH,
    ):
        self.index_path = Path(index_path)
        self.docmap_path = Path(docmap_path)
        self.bm25 = None
        self.chunk_ids: list[str] = []
        self.docmap: dict[str, dict[str, Any]] = {}
        self.corpus_tokens: list[list[str]] = []

    def build(self, chunks_folder: str | Path) -> None:
        """Build BM25 from all JSONL chunk files under chunks_folder."""
        from rank_bm25 import BM25Okapi
        from tqdm import tqdm

        chunks_folder = Path(chunks_folder)
        if not chunks_folder.exists():
            raise FileNotFoundError(f"Chunks folder not found: {chunks_folder}")
        if not chunks_folder.is_dir():
            raise NotADirectoryError(f"Chunks path is not a folder: {chunks_folder}")

        self.chunk_ids = []
        self.docmap = {}
        self.corpus_tokens = []

        jsonl_files = sorted(chunks_folder.rglob("*.jsonl"))
        for jsonl_file in tqdm(jsonl_files, desc="Loading legal chunks", unit="file"):
            for chunk in self._read_jsonl(jsonl_file):
                chunk_id = str(chunk.get("chunk_id", "")).strip()
                text = str(chunk.get("text", "")).strip()
                if not chunk_id or not text:
                    continue

                metadata = dict(chunk.get("metadata") or {})
                merged_metadata = {
                    **metadata,
                    "case_number": chunk.get("case_number", ""),
                    "source": chunk.get("source", ""),
                    "chunk_type": chunk.get("chunk_type", ""),
                    "decision_date": chunk.get("decision_date") or "",
                    "outcome": chunk.get("outcome") or "",
                    "department": chunk.get("department") or "",
                    "commissioner": chunk.get("commissioner") or "",
                }
                doc = {
                    "chunk_id": chunk_id,
                    "case_number": chunk.get("case_number", ""),
                    "chunk_type": chunk.get("chunk_type", ""),
                    "text": text,
                    "metadata": merged_metadata,
                }
                self.chunk_ids.append(chunk_id)
                self.docmap[chunk_id] = doc
                self.corpus_tokens.append(legal_tokenize(text))

        self.bm25 = BM25Okapi(self.corpus_tokens) if self.corpus_tokens else BM25Okapi([["empty"]])

    def search(
        self,
        query: str,
        n_results: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[BM25Result]:
        """Search by BM25 and apply metadata filters after scoring."""
        if self.bm25 is None:
            self.load(self.index_path)

        query_tokens = legal_tokenize(query)
        if not query_tokens or not self.chunk_ids:
            return []

        scores = self.bm25.get_scores(query_tokens)
        ranked_indexes = sorted(
            range(len(scores)),
            key=lambda index: scores[index],
            reverse=True,
        )

        results: list[BM25Result] = []
        for index in ranked_indexes:
            score = float(scores[index])
            if score <= 0:
                break
            chunk_id = self.chunk_ids[index]
            doc = self.docmap.get(chunk_id)
            if not doc:
                continue
            if not self._matches_filters(doc, filters):
                continue
            results.append(
                BM25Result(
                    chunk_id=chunk_id,
                    case_number=str(doc.get("case_number", "")),
                    chunk_type=str(doc.get("chunk_type", "")),
                    text=str(doc.get("text", "")),
                    score=score,
                    metadata=dict(doc.get("metadata") or {}),
                )
            )
            if len(results) >= n_results:
                break

        return results

    def save(self, path: str | Path = DEFAULT_INDEX_PATH) -> None:
        """Pickle the BM25 index and write the JSON document map."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.docmap_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "bm25": self.bm25,
            "chunk_ids": self.chunk_ids,
            "corpus_tokens": self.corpus_tokens,
        }
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False, suffix=".tmp") as tmp:
            pickle.dump(payload, tmp, protocol=pickle.HIGHEST_PROTOCOL)
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
        self.index_path = path

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.docmap_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(self.docmap, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.docmap_path)

    def load(self, path: str | Path = DEFAULT_INDEX_PATH) -> None:
        """Load BM25 pickle and document map JSON."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"BM25 index not found: {path}")

        with open(path, "rb") as f:
            payload = pickle.load(f)
        self.bm25 = payload["bm25"]
        self.chunk_ids = list(payload.get("chunk_ids", []))
        self.corpus_tokens = list(payload.get("corpus_tokens", []))
        self.index_path = path

        if not self.docmap_path.exists():
            raise FileNotFoundError(f"BM25 document map not found: {self.docmap_path}")
        with open(self.docmap_path, "r", encoding="utf-8") as f:
            self.docmap = json.load(f)

    def get_stats(self) -> dict[str, Any]:
        """Return index size and document counts."""
        return {
            "total_docs": len(self.chunk_ids),
            "index_path": str(self.index_path),
            "docmap_path": str(self.docmap_path),
            "index_size_bytes": self.index_path.stat().st_size if self.index_path.exists() else 0,
            "docmap_size_bytes": self.docmap_path.stat().st_size if self.docmap_path.exists() else 0,
        }

    @staticmethod
    def _read_jsonl(path: Path):
        with open(path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc

    @staticmethod
    def _matches_filters(doc: dict[str, Any], filters: Optional[dict[str, Any]]) -> bool:
        if not filters:
            return True

        metadata = doc.get("metadata") or {}
        for key, expected in filters.items():
            if expected is None or expected == "":
                continue
            expected_text = str(expected).lower()

            if key == "year":
                decision_date = str(metadata.get("decision_date", ""))
                if not decision_date.startswith(str(expected)):
                    return False
                continue

            actual = metadata.get(key, doc.get(key, ""))
            if str(actual).lower() != expected_text:
                return False

        return True


class TestBM25Index(unittest.TestCase):
    def setUp(self) -> None:
        if not _deps_available():
            self.skipTest("rank_bm25 is not installed")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.chunks_folder = self.root / "chunks"
        self.chunks_folder.mkdir(parents=True)
        self.index_path = self.root / "indexes" / "bm25_index.pkl"
        self.docmap_path = self.root / "indexes" / "bm25_docmap.json"
        self._write_sample_chunks()

    def tearDown(self) -> None:
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def _write_sample_chunks(self) -> None:
        chunks = [
            {
                "chunk_id": "chunk-1",
                "case_number": "CIC/TEST/A/2024/000001",
                "source": "CIC",
                "decision_date": "2024-01-10",
                "outcome": "PARTIAL",
                "department": "Revenue Department",
                "commissioner": "Commissioner A",
                "chunk_type": "COMMISSION_FINDINGS",
                "text": "[COMMISSION_FINDINGS] File noting disclosure was considered under Section 8(1)(j).",
                "token_count": 12,
                "metadata": {"source_file": "one.txt"},
            },
            {
                "chunk_id": "chunk-2",
                "case_number": "SIC/TEST/A/2023/000002",
                "source": "SIC",
                "decision_date": "2023-02-11",
                "outcome": "REJECTED",
                "department": "Education Department",
                "commissioner": "Commissioner B",
                "chunk_type": "CPIO_REPLY",
                "text": "[CPIO_REPLY] The CPIO replied that records were unavailable.",
                "token_count": 10,
                "metadata": {"source_file": "two.txt"},
            },
            {
                "chunk_id": "chunk-3",
                "case_number": "CIC/TEST/A/2024/000003",
                "source": "CIC",
                "decision_date": "2024-03-12",
                "outcome": "APPEAL_ALLOWED",
                "department": "Finance Department",
                "commissioner": "Commissioner C",
                "chunk_type": "DIRECTIONS",
                "text": "[DIRECTIONS] The CPIO was directed to provide file notings within fifteen days.",
                "token_count": 11,
                "metadata": {"source_file": "three.txt"},
            },
        ]
        path = self.chunks_folder / "sample.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk))
                f.write("\n")

    def test_build_search_save_load(self):
        index = BM25Index(index_path=self.index_path, docmap_path=self.docmap_path)
        index.build(self.chunks_folder)
        self.assertEqual(index.get_stats()["total_docs"], 3)

        results = index.search("file noting exemption 8(1)(j)", n_results=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, "chunk-1")

        filtered = index.search(
            "file noting",
            filters={"source": "CIC", "chunk_type": "DIRECTIONS", "year": "2024"},
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].chunk_id, "chunk-3")

        index.save(self.index_path)
        loaded = BM25Index(index_path=self.index_path, docmap_path=self.docmap_path)
        loaded.load(self.index_path)
        loaded_results = loaded.search("file noting exemption 8(1)(j)")
        self.assertEqual(loaded_results[0].chunk_id, "chunk-1")


def _deps_available() -> bool:
    try:
        import rank_bm25  # noqa: F401
    except ImportError:
        return False
    return True


def _parse_filters(raw_filters: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for item in raw_filters:
        if "=" not in item:
            raise ValueError(f"Invalid filter '{item}'. Use key=value.")
        key, value = item.split("=", 1)
        filters[key.strip()] = value.strip()
    return filters


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestBM25Index)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build/search BM25 index over legal chunks.")
    parser.add_argument("--build", action="store_true", help="Build and save BM25 index.")
    parser.add_argument("--chunks-folder", default=str(DEFAULT_CHUNKS_FOLDER), help="Folder containing LegalChunk JSONL files.")
    parser.add_argument("--index-path", default=str(DEFAULT_INDEX_PATH), help="Path for bm25_index.pkl.")
    parser.add_argument("--docmap-path", default=str(DEFAULT_DOCMAP_PATH), help="Path for bm25_docmap.json.")
    parser.add_argument("--search", help="Run a search query using an existing or newly built index.")
    parser.add_argument("--n-results", type=int, default=20, help="Number of search results.")
    parser.add_argument("--filter", action="append", default=[], help="Metadata filter as key=value. Repeatable.")
    parser.add_argument("--test", action="store_true", help="Run embedded unit tests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.test:
        return _run_tests()

    index = BM25Index(index_path=args.index_path, docmap_path=args.docmap_path)

    if args.build:
        index.build(args.chunks_folder)
        index.save(args.index_path)
        print(json.dumps(index.get_stats(), indent=2))

    if args.search:
        if not args.build:
            index.load(args.index_path)
        filters = _parse_filters(args.filter)
        results = index.search(args.search, n_results=args.n_results, filters=filters)
        for result in results:
            print(result.model_dump_json())
        return 0

    if not args.build:
        print("No action requested. Use --build, --search, or --test.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
