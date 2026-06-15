"""
End-to-end legal corpus indexing pipeline for MAM-RTI.

This script wires together the existing Phase 1 modules without rewriting them:
batch extraction, segmentation, metadata extraction, metadata storage,
legal chunking, embedding storage, and BM25 indexing.

CLI examples:
    python src/pipelines/index_pipeline.py --source data/cic_decisions --mode regex-only
    python src/pipelines/index_pipeline.py --source data/sic_decisions --mode llm
    python src/pipelines/index_pipeline.py --rebuild-index
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pipeline.batch_extractor import batch_extract
from pipeline.legal_chunker import LegalChunker
from pipeline.legal_extractor import LegalExtractor
from pipeline.legal_segmenter import LegalSegmenter
from retrieval.bm25_index import BM25Index
from retrieval.embedding_store import EmbeddingStore
from storage.metadata_store import MetadataStore


DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "pipeline.log"
DEFAULT_CHUNKS_ROOT = PROJECT_ROOT / "data" / "chunks"

logger = logging.getLogger("mam_rti.index_pipeline")


@dataclass
class IndexPipelineSummary:
    pdfs_total: int = 0
    pdfs_extracted: int = 0
    pdfs_skipped: int = 0
    extraction_failed: int = 0
    texts_seen: int = 0
    docs_processed: int = 0
    docs_skipped: int = 0
    chunks_created: int = 0
    embeddings_stored: int = 0
    errors: int = 0
    bm25_rebuilt: bool = False
    elapsed_seconds: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "pdfs_total": self.pdfs_total,
            "pdfs_extracted": self.pdfs_extracted,
            "pdfs_skipped": self.pdfs_skipped,
            "extraction_failed": self.extraction_failed,
            "texts_seen": self.texts_seen,
            "docs_processed": self.docs_processed,
            "docs_skipped": self.docs_skipped,
            "chunks_created": self.chunks_created,
            "embeddings_stored": self.embeddings_stored,
            "errors": self.errors,
            "bm25_rebuilt": self.bm25_rebuilt,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


def configure_logging(log_path: str | Path = DEFAULT_LOG_PATH) -> None:
    """Log pipeline progress to stdout and data/logs/pipeline.log."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(path, encoding="utf-8"),
        ],
        force=True,
    )


class DataIndexingPipeline:
    """Run the existing legal indexing modules in order."""

    def __init__(
        self,
        metadata_store: Optional[MetadataStore] = None,
        segmenter: Optional[LegalSegmenter] = None,
        legal_extractor: Optional[LegalExtractor] = None,
        chunker: Optional[LegalChunker] = None,
        embedding_store: Optional[EmbeddingStore] = None,
        bm25_index: Optional[BM25Index] = None,
        chunks_root: str | Path = DEFAULT_CHUNKS_ROOT,
    ):
        self.metadata_store = metadata_store or MetadataStore()
        self.segmenter = segmenter or LegalSegmenter()
        self.legal_extractor = legal_extractor or LegalExtractor()
        self.chunker = chunker or LegalChunker(chunks_root=chunks_root)
        self.embedding_store = embedding_store or EmbeddingStore()
        self.bm25_index = bm25_index or BM25Index()
        self.chunks_root = Path(chunks_root)

    def run(
        self,
        source: str | Path,
        mode: str = "regex-only",
        output: Optional[str | Path] = None,
        rebuild_index: bool = True,
    ) -> IndexPipelineSummary:
        """Extract, process, embed, and index a source PDF folder."""
        start = time.perf_counter()
        source_path = Path(source)
        output_path = Path(output) if output else self._default_output_folder(source_path)
        use_llm = self._use_llm(mode)
        summary = IndexPipelineSummary()

        logger.info("Starting indexing pipeline | source=%s mode=%s output=%s", source_path, mode, output_path)

        extraction_counts = batch_extract(source_path, output_path)
        summary.pdfs_total = extraction_counts.get("total", 0)
        summary.pdfs_extracted = extraction_counts.get("success", 0)
        summary.pdfs_skipped = extraction_counts.get("skipped", 0)
        summary.extraction_failed = extraction_counts.get("failed", 0)
        logger.info("Extraction complete | %s", extraction_counts)

        text_files = self._text_files(output_path)
        summary.texts_seen = len(text_files)

        try:
            from tqdm import tqdm
        except ImportError:
            tqdm = lambda items, **_: items

        for text_file in tqdm(text_files, desc="Indexing extracted decisions", unit="doc"):
            try:
                processed, chunk_count, embedding_count = self._process_text_file(
                    text_file=text_file,
                    source_folder=source_path,
                    mode=mode,
                    use_llm=use_llm,
                )
                if processed:
                    summary.docs_processed += 1
                    summary.chunks_created += chunk_count
                    summary.embeddings_stored += embedding_count
                else:
                    summary.docs_skipped += 1
            except Exception as exc:
                summary.errors += 1
                logger.exception("Failed to process extracted text %s: %s", text_file, exc)

        if rebuild_index:
            self.rebuild_bm25_index()
            summary.bm25_rebuilt = True

        summary.elapsed_seconds = time.perf_counter() - start
        logger.info("Indexing pipeline complete | %s", summary.as_dict())
        return summary

    def rebuild_bm25_index(self) -> None:
        """Rebuild and save BM25 from data/chunks."""
        logger.info("Rebuilding BM25 index from %s", self.chunks_root)
        self.bm25_index.build(self.chunks_root)
        self.bm25_index.save()
        logger.info("BM25 index rebuilt | %s", self.bm25_index.get_stats())

    def _process_text_file(
        self,
        text_file: Path,
        source_folder: Path,
        mode: str,
        use_llm: bool,
    ) -> tuple[bool, int, int]:
        text = text_file.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            logger.warning("Skipping empty extracted text file: %s", text_file)
            return False, 0, 0

        segmented = self.segmenter.segment(text)
        extracted_case = self.legal_extractor.extract(
            segmented=segmented,
            use_llm=use_llm,
            source_file=str(text_file),
        )

        chunk_path = self._chunk_path(extracted_case.source, extracted_case.case_number)
        if self.metadata_store.check_exists(extracted_case.case_number) and chunk_path.exists():
            logger.info("Skipping already indexed case: %s", extracted_case.case_number)
            return False, 0, 0

        self.metadata_store.save(extracted_case)
        chunks = self.chunker.chunk(segmented, extracted_case, save=True)
        embedded_count = self.embedding_store.embed_and_store(chunks)

        logger.info(
            "Indexed case | case_number=%s mode=%s chunks=%s embeddings=%s",
            extracted_case.case_number,
            mode,
            len(chunks),
            embedded_count,
        )
        return True, len(chunks), embedded_count

    def _chunk_path(self, source: str, case_number: str) -> Path:
        safe_name = self.chunker._safe_filename(case_number)
        return self.chunks_root / (source or "UNKNOWN").upper() / f"{safe_name}.jsonl"

    @staticmethod
    def _text_files(output_path: Path) -> list[Path]:
        return sorted(
            path for path in output_path.rglob("*.txt")
            if path.is_file() and not path.name.endswith("_meta.txt")
        )

    @staticmethod
    def _default_output_folder(source_path: Path) -> Path:
        name = source_path.name.lower()
        if "cic" in name:
            return PROJECT_ROOT / "data" / "extracted" / "cic"
        if "sic" in name:
            return PROJECT_ROOT / "data" / "extracted" / "sic"
        return PROJECT_ROOT / "data" / "extracted" / source_path.name

    @staticmethod
    def _use_llm(mode: str) -> bool:
        normalized = str(mode or "regex-only").strip().lower()
        if normalized not in {"regex-only", "llm"}:
            raise ValueError("mode must be 'regex-only' or 'llm'")
        return normalized == "llm"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MAM-RTI legal indexing pipeline.")
    parser.add_argument("--source", help="Source folder containing CIC/SIC PDFs.")
    parser.add_argument("--output", help="Extracted text output folder. Defaults to data/extracted/{cic|sic|source}.")
    parser.add_argument("--mode", choices=["regex-only", "llm"], default="regex-only")
    parser.add_argument("--rebuild-index", action="store_true", help="Only rebuild BM25 from existing data/chunks unless --source is also provided.")
    parser.add_argument("--no-rebuild-index", action="store_true", help="Skip BM25 rebuild after processing source PDFs.")
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_PATH), help="Pipeline log file. Default: data/logs/pipeline.log")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_file)
    pipeline = DataIndexingPipeline()

    try:
        if args.rebuild_index and not args.source:
            pipeline.rebuild_bm25_index()
            logger.info("BM25 rebuild-only run complete")
            return 0

        if not args.source:
            logger.error("Missing --source. Use --source data/cic_decisions or --rebuild-index.")
            return 2

        summary = pipeline.run(
            source=args.source,
            mode=args.mode,
            output=args.output,
            rebuild_index=not args.no_rebuild_index,
        )
        print(json.dumps(summary.as_dict(), indent=2))
        return 0 if summary.errors == 0 and summary.extraction_failed == 0 else 1
    except Exception as exc:
        logger.exception("Index pipeline failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
