"""
Request-time RTI query pipeline for MAM-RTI.

This module wires the existing RTIAnalysisEngine and ResponseGenerator together.
It does not replace any backend endpoint; it provides a small integration
surface that can be called from the existing FastAPI backend.

Backend integration pattern:

    from pydantic import BaseModel
    from pipelines.query_pipeline import QueryPipeline

    query_pipeline = QueryPipeline()

    class AnalyzeRequest(BaseModel):
        text: str
        type: str = "pio_check"
        department_hint: str | None = None

    @app.post("/analyze")
    async def analyze(req: AnalyzeRequest):
        return query_pipeline.run(
            rtl_text=req.text,
            query_type=req.type,
            department_hint=req.department_hint,
        )
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from engine.rti_analysis_engine import RTIAnalysisEngine, RTIAnalysisResult
from generation.response_templates import GeneratedResponseSet, ResponseGenerator


DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "pipeline.log"
MAX_QUERY_SECONDS = 120.0

logger = logging.getLogger("mam_rti.query_pipeline")


class QueryPipelineResult(BaseModel):
    """Structured backend-ready response for POST /analyze."""

    analysis: RTIAnalysisResult
    responses: GeneratedResponseSet
    elapsed_seconds: float = Field(ge=0.0)


def configure_logging(log_path: str | Path = DEFAULT_LOG_PATH) -> None:
    """Log query progress to stdout and data/logs/pipeline.log."""
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


class QueryPipeline:
    """Run RTI analysis and generate the response package."""

    def __init__(
        self,
        analysis_engine: Optional[RTIAnalysisEngine] = None,
        response_generator: Optional[ResponseGenerator] = None,
        max_seconds: float = MAX_QUERY_SECONDS,
    ):
        self.analysis_engine = analysis_engine or RTIAnalysisEngine()
        self.response_generator = response_generator or ResponseGenerator()
        self.max_seconds = max_seconds

    def run(
        self,
        rtl_text: Optional[str] = None,
        query_type: str = "pio_check",
        department_hint: Optional[str] = None,
        appellant_name: Optional[str] = None,
        rti_date: Optional[str] = None,
        rti_subject: Optional[str] = None,
        reply_date: Optional[str] = None,
        **kwargs: Any,
    ) -> QueryPipelineResult:
        """
        Analyze one OCR'd RTI document or typed query and generate responses.

        Accepts both `rtl_text` from the user specification and `rti_text` for
        callers that use the conventional spelling.
        """
        start = time.perf_counter()
        text = (rtl_text if rtl_text is not None else kwargs.get("rti_text", "") or "").strip()
        logger.info("Starting query pipeline | type=%s department_hint=%s", query_type, department_hint)

        analysis = self.analysis_engine.analyze(
            rti_text=text,
            analysis_type=self._normalize_query_type(query_type),
            department_hint=department_hint,
        )
        responses = self.response_generator.generate_all(
            analysis=analysis,
            appellant_name=appellant_name,
            rti_date=rti_date,
            rti_subject=rti_subject,
            reply_date=reply_date,
        )

        elapsed = time.perf_counter() - start
        if elapsed > self.max_seconds:
            logger.warning("Query pipeline exceeded target time | elapsed=%.3fs", elapsed)
        else:
            logger.info("Query pipeline complete | elapsed=%.3fs", elapsed)

        return QueryPipelineResult(
            analysis=analysis,
            responses=responses,
            elapsed_seconds=round(elapsed, 3),
        )

    @staticmethod
    def _normalize_query_type(query_type: str) -> str:
        value = str(query_type or "pio_check").strip().lower()
        mapping = {
            "pio_check": "pio_check",
            "pio_assistance": "pio_check",
            "appeal_prediction": "appeal_prediction",
            "appeal_analysis": "appeal_prediction",
            "exemption_check": "exemption_check",
        }
        return mapping.get(value, "pio_check")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one RTI query through analysis and response generation.")
    parser.add_argument("--text", help="RTI query text. Use --text-file for longer OCR text.")
    parser.add_argument("--text-file", help="Path to OCR text file.")
    parser.add_argument("--type", default="pio_check", help="pio_check, appeal_prediction, or exemption_check.")
    parser.add_argument("--department-hint")
    parser.add_argument("--appellant-name")
    parser.add_argument("--rti-date")
    parser.add_argument("--rti-subject")
    parser.add_argument("--reply-date")
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_PATH), help="Pipeline log file. Default: data/logs/pipeline.log")
    return parser.parse_args()


def _read_input_text(args: argparse.Namespace) -> str:
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8", errors="replace")
    return args.text or ""


def main() -> int:
    args = parse_args()
    configure_logging(args.log_file)

    text = _read_input_text(args)
    if not text.strip():
        logger.error("No RTI text provided. Use --text or --text-file.")
        return 2

    try:
        result = QueryPipeline().run(
            rtl_text=text,
            query_type=args.type,
            department_hint=args.department_hint,
            appellant_name=args.appellant_name,
            rti_date=args.rti_date,
            rti_subject=args.rti_subject,
            reply_date=args.reply_date,
        )
        print(result.model_dump_json(indent=2))
        return 0
    except Exception as exc:
        logger.exception("Query pipeline failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
