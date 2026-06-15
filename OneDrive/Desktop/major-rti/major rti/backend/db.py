"""
RTI Intelligence System — Immutable Audit Trail (SQLite)

Design principles:
  • Append-only: core audit fields are NEVER updated or deleted.
  • Hash-chain integrity: every record's `current_hash` is the SHA-256 of
    (previous_hash ‖ audit_id ‖ timestamp ‖ key fields), making tampering
    detectable.
  • PIO decisions are recorded in dedicated columns that start as NULL/PENDING
    and may be set exactly once via `update_pio_decision`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH: Path = Path(__file__).resolve().parent / "rti_audit.db"
GENESIS_HASH: str = "0" * 64  # SHA-256 zero hash for the first record

# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------


class AuditRecord(BaseModel):
    """Immutable audit record for a single RTI analysis event."""

    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # --- Input ---
    raw_input_text: str = ""
    extracted_text_ocr: str = ""
    ocr_confidence: float = 0.0

    # --- Language ---
    language_detected: str = ""

    # --- System recommendation (immutable once written) ---
    system_recommended_department: str = ""
    system_confidence_band: str = "LOW"  # HIGH / MEDIUM / LOW
    system_reasoning: str = ""
    alternative_departments: list[str] = Field(default_factory=list)

    # --- Phase 1: Information Extraction & Exemption Analysis ---
    extracted_entities: list[str] = Field(default_factory=list)
    information_type: str = ""
    rule_engine_flags: list[str] = Field(default_factory=list)
    pio_exemption_override: Optional[str] = None

    # --- PIO decision (set later via update_pio_decision) ---
    pio_action_taken: str = "PENDING"  # APPROVED / OVERRIDDEN / REJECTED / PENDING
    pio_override_department: Optional[str] = None
    pio_comments: Optional[str] = None
    legal_disclaimer_accepted: bool = False

    # --- Hash chain ---
    previous_hash: str = ""
    current_hash: str = ""


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_trail (
    audit_id                    TEXT PRIMARY KEY,
    timestamp                   TEXT NOT NULL,

    raw_input_text              TEXT NOT NULL DEFAULT '',
    extracted_text_ocr          TEXT NOT NULL DEFAULT '',
    ocr_confidence              REAL NOT NULL DEFAULT 0.0,

    language_detected           TEXT NOT NULL DEFAULT '',

    system_recommended_department TEXT NOT NULL DEFAULT '',
    system_confidence_band      TEXT NOT NULL DEFAULT 'LOW',
    system_reasoning            TEXT NOT NULL DEFAULT '',
    alternative_departments     TEXT NOT NULL DEFAULT '[]',

    extracted_entities          TEXT NOT NULL DEFAULT '[]',
    information_type            TEXT NOT NULL DEFAULT '',
    rule_engine_flags           TEXT NOT NULL DEFAULT '[]',
    pio_exemption_override      TEXT,

    pio_action_taken            TEXT NOT NULL DEFAULT 'PENDING',
    pio_override_department     TEXT,
    pio_comments                TEXT,
    legal_disclaimer_accepted   INTEGER NOT NULL DEFAULT 0,

    previous_hash               TEXT NOT NULL DEFAULT '',
    current_hash                TEXT NOT NULL DEFAULT ''
);
"""


def _get_connection() -> sqlite3.Connection:
    """Return a connection with row-factory enabled."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Create the audit_trail table if it does not already exist."""
    with _get_connection() as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()


# ---------------------------------------------------------------------------
# Hash-chain helpers
# ---------------------------------------------------------------------------


def _compute_hash(
    previous_hash: str,
    audit_id: str,
    timestamp: str,
    raw_input_text: str,
    system_recommended_department: str,
    system_confidence_band: str,
    system_reasoning: str,
) -> str:
    """Compute SHA-256 hash for the chain.

    Hash = SHA-256(previous_hash + audit_id + timestamp + key fields)
    """
    payload = "|".join(
        [
            previous_hash,
            audit_id,
            timestamp,
            raw_input_text,
            system_recommended_department,
            system_confidence_band,
            system_reasoning,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fetch_last_hash(conn: sqlite3.Connection) -> str:
    """Return the current_hash of the most recent record, or GENESIS_HASH."""
    row = conn.execute(
        "SELECT current_hash FROM audit_trail ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return GENESIS_HASH
    return row["current_hash"]


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def log_analysis(record: AuditRecord) -> str:
    """Insert a new audit record and return its audit_id.

    The record's hash-chain fields (previous_hash, current_hash) are
    computed automatically — any values already on the record are
    overwritten to guarantee chain integrity.

    Args:
        record: The AuditRecord to persist.

    Returns:
        The audit_id of the inserted record.
    """
    with _get_connection() as conn:
        # Chain linking
        previous_hash = _fetch_last_hash(conn)
        current_hash = _compute_hash(
            previous_hash=previous_hash,
            audit_id=record.audit_id,
            timestamp=record.timestamp,
            raw_input_text=record.raw_input_text,
            system_recommended_department=record.system_recommended_department,
            system_confidence_band=record.system_confidence_band,
            system_reasoning=record.system_reasoning,
        )
        record.previous_hash = previous_hash
        record.current_hash = current_hash

        conn.execute(
            """
            INSERT INTO audit_trail (
                audit_id, timestamp,
                raw_input_text, extracted_text_ocr, ocr_confidence,
                language_detected,
                system_recommended_department, system_confidence_band,
                system_reasoning, alternative_departments,
                extracted_entities, information_type, rule_engine_flags, pio_exemption_override,
                pio_action_taken, pio_override_department, pio_comments,
                legal_disclaimer_accepted,
                previous_hash, current_hash
            ) VALUES (
                :audit_id, :timestamp,
                :raw_input_text, :extracted_text_ocr, :ocr_confidence,
                :language_detected,
                :system_recommended_department, :system_confidence_band,
                :system_reasoning, :alternative_departments,
                :extracted_entities, :information_type, :rule_engine_flags, :pio_exemption_override,
                :pio_action_taken, :pio_override_department, :pio_comments,
                :legal_disclaimer_accepted,
                :previous_hash, :current_hash
            )
            """,
            {
                "audit_id": record.audit_id,
                "timestamp": record.timestamp,
                "raw_input_text": record.raw_input_text,
                "extracted_text_ocr": record.extracted_text_ocr,
                "ocr_confidence": record.ocr_confidence,
                "language_detected": record.language_detected,
                "system_recommended_department": record.system_recommended_department,
                "system_confidence_band": record.system_confidence_band,
                "system_reasoning": record.system_reasoning,
                "alternative_departments": json.dumps(
                    record.alternative_departments, ensure_ascii=False
                ),
                "extracted_entities": json.dumps(
                    record.extracted_entities, ensure_ascii=False
                ),
                "information_type": record.information_type,
                "rule_engine_flags": json.dumps(
                    record.rule_engine_flags, ensure_ascii=False
                ),
                "pio_exemption_override": record.pio_exemption_override,
                "pio_action_taken": record.pio_action_taken,
                "pio_override_department": record.pio_override_department,
                "pio_comments": record.pio_comments,
                "legal_disclaimer_accepted": int(record.legal_disclaimer_accepted),
                "previous_hash": record.previous_hash,
                "current_hash": record.current_hash,
            },
        )
        conn.commit()

    return record.audit_id


def update_pio_decision(
    audit_id: str,
    action: str,
    override_dept: Optional[str] = None,
    comments: Optional[str] = None,
    disclaimer_accepted: bool = False,
    exemption_override: Optional[str] = None,
) -> bool:
    """Record the PIO's decision on an existing audit record.

    Only the PIO-specific columns are updated — the system
    recommendation, hash chain, and all other core fields remain
    immutable.

    Args:
        audit_id:            UUID of the record to update.
        action:              One of APPROVED / OVERRIDDEN / REJECTED.
        override_dept:       Department chosen by PIO (required if OVERRIDDEN).
        comments:            Free-text PIO comments.
        disclaimer_accepted: Whether the PIO accepted the legal disclaimer.

    Returns:
        True if exactly one row was updated, False otherwise.

    Raises:
        ValueError: If action is not a valid PIO action.
        ValueError: If the record has already been decided (not PENDING).
    """
    valid_actions = {"APPROVED", "OVERRIDDEN", "REJECTED"}
    if action not in valid_actions:
        raise ValueError(
            f"Invalid PIO action '{action}'. Must be one of {valid_actions}."
        )

    with _get_connection() as conn:
        # Guard: only allow updating PENDING records
        row = conn.execute(
            "SELECT pio_action_taken FROM audit_trail WHERE audit_id = ?",
            (audit_id,),
        ).fetchone()

        if row is None:
            return False

        if row["pio_action_taken"] != "PENDING":
            raise ValueError(
                f"Record {audit_id} already has PIO action "
                f"'{row['pio_action_taken']}'. Cannot modify a decided record."
            )

        cursor = conn.execute(
            """
            UPDATE audit_trail
            SET pio_action_taken         = ?,
                pio_override_department  = ?,
                pio_comments             = ?,
                legal_disclaimer_accepted = ?,
                pio_exemption_override   = ?
            WHERE audit_id = ? AND pio_action_taken = 'PENDING'
            """,
            (
                action,
                override_dept,
                comments,
                int(disclaimer_accepted),
                exemption_override,
                audit_id,
            ),
        )
        conn.commit()

    return cursor.rowcount == 1


def _row_to_record(row: sqlite3.Row) -> AuditRecord:
    """Convert a sqlite3.Row to an AuditRecord."""
    data = dict(row)
    data["alternative_departments"] = json.loads(
        data.get("alternative_departments", "[]")
    )
    data["extracted_entities"] = json.loads(
        data.get("extracted_entities", "[]")
    )
    data["rule_engine_flags"] = json.loads(
        data.get("rule_engine_flags", "[]")
    )
    data["legal_disclaimer_accepted"] = bool(data.get("legal_disclaimer_accepted", 0))
    return AuditRecord(**data)


def get_audit_trail(limit: int = 50) -> list[AuditRecord]:
    """Return the most recent audit records, newest first.

    Args:
        limit: Maximum number of records to return (default 50).

    Returns:
        A list of AuditRecord instances.
    """
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_trail ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [_row_to_record(r) for r in rows]


def get_record(audit_id: str) -> Optional[AuditRecord]:
    """Fetch a single audit record by its UUID.

    Args:
        audit_id: The UUID of the record.

    Returns:
        The matching AuditRecord, or None if not found.
    """
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audit_trail WHERE audit_id = ?",
            (audit_id,),
        ).fetchone()

    if row is None:
        return None
    return _row_to_record(row)


def verify_chain(limit: int = 0) -> tuple[bool, list[str]]:
    """Verify the integrity of the hash chain.

    Walks the audit trail from oldest to newest and checks that each
    record's `current_hash` matches the recomputed hash and that its
    `previous_hash` matches the preceding record's `current_hash`.

    Args:
        limit: If > 0, only verify the last *limit* records.

    Returns:
        A tuple of (is_valid, list_of_error_messages).
    """
    query = "SELECT * FROM audit_trail ORDER BY timestamp ASC"
    if limit > 0:
        query += f" LIMIT {limit}"

    with _get_connection() as conn:
        rows = conn.execute(query).fetchall()

    errors: list[str] = []
    expected_prev = GENESIS_HASH

    for row in rows:
        r = dict(row)
        # Check previous_hash linkage
        if r["previous_hash"] != expected_prev:
            errors.append(
                f"Record {r['audit_id']}: previous_hash mismatch. "
                f"Expected {expected_prev}, got {r['previous_hash']}."
            )

        # Recompute hash
        recomputed = _compute_hash(
            previous_hash=r["previous_hash"],
            audit_id=r["audit_id"],
            timestamp=r["timestamp"],
            raw_input_text=r["raw_input_text"],
            system_recommended_department=r["system_recommended_department"],
            system_confidence_band=r["system_confidence_band"],
            system_reasoning=r["system_reasoning"],
        )
        if r["current_hash"] != recomputed:
            errors.append(
                f"Record {r['audit_id']}: current_hash mismatch. "
                f"Expected {recomputed}, got {r['current_hash']}."
            )

        expected_prev = r["current_hash"]

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# Module-level auto-init
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {DB_PATH}")
    print("Tables ready. Hash chain uses genesis hash:", GENESIS_HASH)
