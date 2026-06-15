"""
Local metadata store for extracted CIC/SIC case metadata.

Storage:
  1. SQLite database at data/db/cases.db
  2. Human-readable JSON sidecars at data/metadata/{source}/{year}/{case_number}.json

No ORM is used. SQLite from the Python standard library is the only database
dependency.

Usage example:
    from models.extracted_case import ExtractedCase
    from storage.metadata_store import MetadataStore

    store = MetadataStore()
    case = ExtractedCase(
        case_number="CIC/MFINB/A/2024/001234",
        decision_date="2025-04-05",
        source="CIC",
        source_file="data/extracted/cic/sample.txt",
        sections_invoked=["8(1)(j)", "10"],
        outcome="PARTIAL",
        penalty_imposed=False,
        public_interest_discussed=True,
        extraction_confidence=0.91,
    )
    store.save(case)
    found = store.get_by_case_number("CIC/MFINB/A/2024/001234")
    results = store.search(outcome="PARTIAL", section="8(1)(j)")
    stats = store.get_stats()
    jsonl_path = store.export_all_json()

Run tests:
    python src/storage/metadata_store.py --test
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from models.extracted_case import ExtractedCase


DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "cases.db"
DEFAULT_METADATA_ROOT = PROJECT_ROOT / "data" / "metadata"
DEFAULT_EXPORT_PATH = PROJECT_ROOT / "data" / "metadata" / "all_cases.jsonl"


CREATE_CASES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cases (
    case_number TEXT PRIMARY KEY,
    appeal_number TEXT,
    decision_date TEXT,
    hearing_date TEXT,
    commissioner_name TEXT,
    appellant_name TEXT,
    respondent_name TEXT,
    department TEXT,
    ministry TEXT,
    cpio_name TEXT,
    faa_name TEXT,
    rti_request_summary TEXT,
    sections_invoked TEXT NOT NULL DEFAULT '[]',
    outcome TEXT,
    penalty_imposed INTEGER NOT NULL DEFAULT 0,
    penalty_amount INTEGER,
    key_findings TEXT NOT NULL DEFAULT '[]',
    public_interest_discussed INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    source_file TEXT NOT NULL DEFAULT '',
    extraction_confidence REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_cases_case_number ON cases(case_number);",
    "CREATE INDEX IF NOT EXISTS idx_cases_decision_date ON cases(decision_date);",
    "CREATE INDEX IF NOT EXISTS idx_cases_outcome ON cases(outcome);",
    "CREATE INDEX IF NOT EXISTS idx_cases_department ON cases(department);",
    "CREATE INDEX IF NOT EXISTS idx_cases_source ON cases(source);",
]

JSON_LIST_FIELDS = {
    "sections_invoked",
    "rti_sections",
    "exemption_sections",
    "information_requested",
    "court_references",
    "circular_references",
    "commission_observations",
    "entities",
    "entities_person",
    "entities_authority",
    "entities_department",
    "entities_location",
    "reasoning_pattern",
    "key_findings",
}

INTEGER_BOOL_FIELDS = {"penalty_imposed", "public_interest_discussed"}

EXTRA_CASE_COLUMNS = {
    "commission": "TEXT",
    "public_authority": "TEXT",
    "rti_application_date": "TEXT",
    "cpio_reply_date": "TEXT",
    "first_appeal_date": "TEXT",
    "faa_order_date": "TEXT",
    "second_appeal_date": "TEXT",
    "facts": "TEXT",
    "information_requested": "TEXT NOT NULL DEFAULT '[]'",
    "grounds_for_appeal": "TEXT",
    "rti_sections": "TEXT NOT NULL DEFAULT '[]'",
    "exemption_sections": "TEXT NOT NULL DEFAULT '[]'",
    "court_references": "TEXT NOT NULL DEFAULT '[]'",
    "circular_references": "TEXT NOT NULL DEFAULT '[]'",
    "commission_observations": "TEXT NOT NULL DEFAULT '[]'",
    "final_order": "TEXT",
    "reasoning_pattern": "TEXT NOT NULL DEFAULT '[]'",
    "pio_learning_signal": "TEXT",
    "entities": "TEXT NOT NULL DEFAULT '[]'",
    "entities_person": "TEXT NOT NULL DEFAULT '[]'",
    "entities_authority": "TEXT NOT NULL DEFAULT '[]'",
    "entities_department": "TEXT NOT NULL DEFAULT '[]'",
    "entities_location": "TEXT NOT NULL DEFAULT '[]'",
    "precedent_chunk": "TEXT",
}


UPSERT_CASE_SQL = """
INSERT INTO cases (
    case_number,
    appeal_number,
    decision_date,
    hearing_date,
    commissioner_name,
    appellant_name,
    respondent_name,
    department,
    ministry,
    cpio_name,
    faa_name,
    rti_request_summary,
    sections_invoked,
    outcome,
    penalty_imposed,
    penalty_amount,
    key_findings,
    public_interest_discussed,
    source,
    source_file,
    extraction_confidence,
    created_at,
    updated_at
) VALUES (
    :case_number,
    :appeal_number,
    :decision_date,
    :hearing_date,
    :commissioner_name,
    :appellant_name,
    :respondent_name,
    :department,
    :ministry,
    :cpio_name,
    :faa_name,
    :rti_request_summary,
    :sections_invoked,
    :outcome,
    :penalty_imposed,
    :penalty_amount,
    :key_findings,
    :public_interest_discussed,
    :source,
    :source_file,
    :extraction_confidence,
    :created_at,
    :updated_at
)
ON CONFLICT(case_number) DO UPDATE SET
    appeal_number = excluded.appeal_number,
    decision_date = excluded.decision_date,
    hearing_date = excluded.hearing_date,
    commissioner_name = excluded.commissioner_name,
    appellant_name = excluded.appellant_name,
    respondent_name = excluded.respondent_name,
    department = excluded.department,
    ministry = excluded.ministry,
    cpio_name = excluded.cpio_name,
    faa_name = excluded.faa_name,
    rti_request_summary = excluded.rti_request_summary,
    sections_invoked = excluded.sections_invoked,
    outcome = excluded.outcome,
    penalty_imposed = excluded.penalty_imposed,
    penalty_amount = excluded.penalty_amount,
    key_findings = excluded.key_findings,
    public_interest_discussed = excluded.public_interest_discussed,
    source = excluded.source,
    source_file = excluded.source_file,
    extraction_confidence = excluded.extraction_confidence,
    updated_at = excluded.updated_at;
"""


class MetadataStore:
    """SQLite + JSON sidecar store for ExtractedCase records."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        metadata_root: str | Path = DEFAULT_METADATA_ROOT,
        export_path: str | Path = DEFAULT_EXPORT_PATH,
    ):
        self.db_path = Path(db_path)
        self.metadata_root = Path(metadata_root)
        self.export_path = Path(export_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def save(self, case: ExtractedCase) -> bool:
        """Upsert a case into SQLite and write its JSON sidecar."""
        now = self._now()
        existing_created_at = self._get_created_at(case.case_number)
        payload = self._case_to_row(case)
        payload["created_at"] = existing_created_at or now
        payload["updated_at"] = now

        with self._connect() as conn:
            self._dynamic_upsert(conn, payload)
            conn.commit()

        self._write_case_json(case, payload["created_at"], payload["updated_at"])
        return True

    def get_by_case_number(self, case_number: str) -> Optional[ExtractedCase]:
        """Fetch one case by case number."""
        normalized = self._normalize_case_number(case_number)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM cases WHERE case_number = ?",
                (normalized,),
            ).fetchone()
        return self._row_to_case(row) if row else None

    def search(
        self,
        department: Optional[str] = None,
        outcome: Optional[str] = None,
        year: Optional[int | str] = None,
        section: Optional[str] = None,
    ) -> list[ExtractedCase]:
        """Search by any combination of department, outcome, year, and section."""
        clauses: list[str] = []
        params: list[Any] = []

        if department:
            clauses.append("LOWER(COALESCE(department, '')) LIKE ?")
            params.append(f"%{department.lower()}%")

        if outcome:
            clauses.append("outcome = ?")
            params.append(str(outcome).upper())

        if year:
            clauses.append("substr(decision_date, 1, 4) = ?")
            params.append(str(year))

        if section:
            normalized_section = self._normalize_section(section)
            clauses.append("sections_invoked LIKE ?")
            params.append(f"%{normalized_section}%")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM cases {where_sql} ORDER BY decision_date DESC, case_number ASC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        # SQLite LIKE on a JSON string is fast and simple, but do an exact
        # post-filter so section '8(1)(j)' does not accidentally match noise.
        cases = [self._row_to_case(row) for row in rows]
        if section:
            normalized_section = self._normalize_section(section).lower()
            cases = [
                case for case in cases
                if any(s.lower() == normalized_section for s in case.sections_invoked)
            ]
        return cases

    def get_stats(self) -> dict[str, Any]:
        """Return total cases plus breakdowns by outcome, year, and department."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS count FROM cases").fetchone()["count"]
            by_outcome = self._count_group(conn, "outcome")
            by_department = self._count_group(conn, "department")
            year_rows = conn.execute(
                """
                SELECT substr(decision_date, 1, 4) AS year, COUNT(*) AS count
                FROM cases
                WHERE decision_date IS NOT NULL AND decision_date != ''
                GROUP BY year
                ORDER BY year
                """
            ).fetchall()
            by_source = self._count_group(conn, "source")

        return {
            "total_cases": total,
            "by_outcome": by_outcome,
            "by_year": {row["year"]: row["count"] for row in year_rows if row["year"]},
            "by_department": by_department,
            "by_source": by_source,
        }

    def export_all_json(self) -> str:
        """Export all SQLite records to one JSONL file for downstream indexing."""
        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cases ORDER BY decision_date ASC, case_number ASC"
            ).fetchall()

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.export_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            for row in rows:
                case = self._row_to_case(row)
                tmp.write(json.dumps(case.model_dump(), ensure_ascii=False))
                tmp.write("\n")
            tmp_path = Path(tmp.name)

        tmp_path.replace(self.export_path)
        return str(self.export_path)

    def check_exists(self, case_number: str) -> bool:
        """Return True when a case_number already exists in SQLite."""
        normalized = self._normalize_case_number(case_number)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM cases WHERE case_number = ? LIMIT 1",
                (normalized,),
            ).fetchone()
        return row is not None

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(CREATE_CASES_TABLE_SQL)
            self._ensure_extra_columns(conn)
            for sql in CREATE_INDEXES_SQL:
                conn.execute(sql)
            conn.commit()

    def _ensure_extra_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(cases)").fetchall()
        }
        for column, column_type in EXTRA_CASE_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE cases ADD COLUMN {column} {column_type}")

    def _dynamic_upsert(self, conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
        columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(cases)").fetchall()
            if row["name"] in payload
        ]
        placeholders = ", ".join(f":{column}" for column in columns)
        column_sql = ", ".join(columns)
        updates = ", ".join(
            f"{column} = excluded.{column}"
            for column in columns
            if column not in {"case_number", "created_at"}
        )
        sql = (
            f"INSERT INTO cases ({column_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT(case_number) DO UPDATE SET {updates}"
        )
        conn.execute(sql, payload)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")
        try:
            yield conn
        finally:
            conn.close()

    def _case_to_row(self, case: ExtractedCase) -> dict[str, Any]:
        data = case.model_dump()
        data["case_number"] = self._normalize_case_number(data["case_number"])
        for field in JSON_LIST_FIELDS:
            data[field] = json.dumps(data.get(field, []), ensure_ascii=False)
        for field in INTEGER_BOOL_FIELDS:
            data[field] = int(bool(data.get(field)))
        return data

    def _row_to_case(self, row: sqlite3.Row) -> ExtractedCase:
        data = dict(row)
        data.pop("created_at", None)
        data.pop("updated_at", None)
        for field in JSON_LIST_FIELDS:
            if field in data:
                data[field] = json.loads(data.get(field) or "[]")
        for field in INTEGER_BOOL_FIELDS:
            if field in data:
                data[field] = bool(data.get(field))
        return ExtractedCase(**data)

    def _write_case_json(self, case: ExtractedCase, created_at: str, updated_at: str) -> None:
        payload = case.model_dump()
        payload["case_number"] = self._normalize_case_number(case.case_number)
        payload["created_at"] = created_at
        payload["updated_at"] = updated_at

        path = self._json_path_for_case(case)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)

    def _json_path_for_case(self, case: ExtractedCase) -> Path:
        year = self._year_for_case(case)
        source = (case.source or "CIC").upper()
        filename = self._safe_filename(self._normalize_case_number(case.case_number)) + ".json"
        return self.metadata_root / source / year / filename

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-") or "UNKNOWN"

    @staticmethod
    def _year_for_case(case: ExtractedCase) -> str:
        if case.decision_date and re.match(r"^\d{4}-", case.decision_date):
            return case.decision_date[:4]
        match = re.search(r"/(20\d{2}|19\d{2})/", case.case_number)
        return match.group(1) if match else "unknown"

    def _get_created_at(self, case_number: str) -> Optional[str]:
        normalized = self._normalize_case_number(case_number)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM cases WHERE case_number = ?",
                (normalized,),
            ).fetchone()
        return row["created_at"] if row else None

    @staticmethod
    def _normalize_case_number(case_number: str) -> str:
        text = str(case_number or "").strip().replace("\\", "/")
        text = re.sub(r"[_-]+", "/", text)
        text = re.sub(r"/+", "/", text)
        return text.upper().strip("/") or "UNKNOWN"

    @staticmethod
    def _normalize_section(section: str) -> str:
        text = str(section or "").strip()
        text = re.sub(r"(?i)^section\s+", "", text)
        text = re.sub(r"\s+", "", text)
        return text

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _count_group(conn: sqlite3.Connection, column: str) -> dict[str, int]:
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF({column}, ''), 'UNKNOWN') AS label, COUNT(*) AS count
            FROM cases
            GROUP BY label
            ORDER BY count DESC, label ASC
            """
        ).fetchall()
        return {row["label"]: row["count"] for row in rows}


class TestMetadataStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = MetadataStore(
            db_path=root / "data" / "db" / "cases.db",
            metadata_root=root / "data" / "metadata",
            export_path=root / "data" / "metadata" / "all_cases.jsonl",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _case(
        self,
        case_number: str = "CIC/MFINB/A/2024/001234",
        department: str = "Department of Revenue",
        outcome: str = "PARTIAL",
        decision_date: str = "2025-04-05",
        sections: Optional[list[str]] = None,
    ) -> ExtractedCase:
        return ExtractedCase(
            case_number=case_number,
            decision_date=decision_date,
            department=department,
            outcome=outcome,
            sections_invoked=sections or ["8(1)(j)", "10"],
            source="CIC",
            source_file="sample.pdf",
            penalty_imposed=False,
            public_interest_discussed=True,
            key_findings=["Finding one", "Finding two"],
            extraction_confidence=0.91,
        )

    def test_save_get_and_exists(self):
        case = self._case()
        self.assertTrue(self.store.save(case))
        self.assertTrue(self.store.check_exists(case.case_number))

        found = self.store.get_by_case_number(case.case_number)
        self.assertIsNotNone(found)
        self.assertEqual(found.case_number, case.case_number)
        self.assertEqual(found.sections_invoked, ["8(1)(j)", "10"])

    def test_upsert_updates_not_duplicates(self):
        self.store.save(self._case(outcome="PARTIAL"))
        self.store.save(self._case(outcome="APPEAL_ALLOWED", sections=["6(3)"]))

        stats = self.store.get_stats()
        found = self.store.get_by_case_number("CIC/MFINB/A/2024/001234")
        self.assertEqual(stats["total_cases"], 1)
        self.assertEqual(found.outcome, "APPEAL_ALLOWED")
        self.assertEqual(found.sections_invoked, ["6(3)"])

    def test_search_and_stats_and_export(self):
        self.store.save(self._case())
        self.store.save(
            self._case(
                case_number="SIC/CG/A/2023/000111",
                department="Education Department",
                outcome="REJECTED",
                decision_date="2023-08-01",
                sections=["8(1)(d)"],
            )
        )

        revenue_results = self.store.search(department="Revenue")
        partial_results = self.store.search(outcome="PARTIAL")
        year_results = self.store.search(year=2023)
        section_results = self.store.search(section="8(1)(j)")
        stats = self.store.get_stats()
        export_path = self.store.export_all_json()

        self.assertEqual(len(revenue_results), 1)
        self.assertEqual(len(partial_results), 1)
        self.assertEqual(len(year_results), 1)
        self.assertEqual(len(section_results), 1)
        self.assertEqual(stats["total_cases"], 2)
        self.assertEqual(stats["by_outcome"]["PARTIAL"], 1)
        self.assertEqual(stats["by_year"]["2025"], 1)
        self.assertTrue(Path(export_path).exists())
        self.assertEqual(len(Path(export_path).read_text(encoding="utf-8").splitlines()), 2)


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestMetadataStore)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def _usage_example() -> int:
    store = MetadataStore()
    case = ExtractedCase(
        case_number="CIC/MFINB/A/2024/001234",
        decision_date="2025-04-05",
        department="Department of Revenue",
        outcome="PARTIAL",
        sections_invoked=["8(1)(j)", "10"],
        source="CIC",
        source_file="data/extracted/cic/CIC_MFINB_A_2024_001234.txt",
        penalty_imposed=False,
        public_interest_discussed=True,
        key_findings=["CPIO denial required reconsideration", "Personal identifiers should be redacted"],
        extraction_confidence=0.91,
    )
    store.save(case)
    print("Found:", store.get_by_case_number(case.case_number).model_dump())
    print("Search:", [item.case_number for item in store.search(outcome="PARTIAL", section="8(1)(j)")])
    print("Stats:", json.dumps(store.get_stats(), indent=2))
    print("Export:", store.export_all_json())
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local metadata store for extracted CIC/SIC cases.")
    parser.add_argument("--test", action="store_true", help="Run embedded unit tests.")
    parser.add_argument("--example", action="store_true", help="Run save -> search -> stats usage example.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.test:
        return _run_tests()
    if args.example:
        return _usage_example()
    print("No action requested. Use --test or --example.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
