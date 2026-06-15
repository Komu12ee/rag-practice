"""
Pydantic models for structured CIC/SIC decision metadata extraction.

Install requirements:
    pip install pydantic
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


VALID_OUTCOMES = {"APPEAL_ALLOWED", "APPEAL_DISPOSED", "REJECTED", "PARTIAL", "PENALTY"}
VALID_SOURCES = {"CIC", "SIC", "COURT", "CIRCULAR", "RTI_ACT", "PREVIOUS_RTI"}


class ExtractedCase(BaseModel):
    """Structured metadata extracted from a segmented CIC/SIC decision."""

    case_number: str
    commission: Optional[str] = None
    appeal_number: Optional[str] = None
    decision_date: Optional[str] = None
    hearing_date: Optional[str] = None
    commissioner_name: Optional[str] = None
    appellant_name: Optional[str] = None
    respondent_name: Optional[str] = None
    public_authority: Optional[str] = None
    department: Optional[str] = None
    ministry: Optional[str] = None
    cpio_name: Optional[str] = None
    faa_name: Optional[str] = None
    rti_application_date: Optional[str] = None
    cpio_reply_date: Optional[str] = None
    first_appeal_date: Optional[str] = None
    faa_order_date: Optional[str] = None
    second_appeal_date: Optional[str] = None
    facts: Optional[str] = None
    information_requested: list[str] = Field(default_factory=list)
    grounds_for_appeal: Optional[str] = None
    rti_request_summary: Optional[str] = None
    sections_invoked: list[str] = Field(default_factory=list)
    rti_sections: list[str] = Field(default_factory=list)
    exemption_sections: list[str] = Field(default_factory=list)
    court_references: list[str] = Field(default_factory=list)
    circular_references: list[str] = Field(default_factory=list)
    commission_observations: list[str] = Field(default_factory=list)
    final_order: Optional[str] = None
    outcome: Optional[str] = None
    reasoning_pattern: list[str] = Field(default_factory=list)
    pio_learning_signal: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    entities_person: list[str] = Field(default_factory=list)
    entities_authority: list[str] = Field(default_factory=list)
    entities_department: list[str] = Field(default_factory=list)
    entities_location: list[str] = Field(default_factory=list)
    precedent_chunk: Optional[str] = None
    penalty_imposed: bool = False
    penalty_amount: Optional[int] = None
    key_findings: list[str] = Field(default_factory=list)
    public_interest_discussed: bool = False
    source: str
    source_file: str = ""
    extraction_confidence: float = Field(0.0, ge=0.0, le=1.0)

    @field_validator("case_number", "source", mode="before")
    @classmethod
    def _required_string(cls, value) -> str:
        text = "" if value is None else str(value).strip()
        return text

    @field_validator(
        "appeal_number",
        "commission",
        "decision_date",
        "hearing_date",
        "rti_application_date",
        "cpio_reply_date",
        "first_appeal_date",
        "faa_order_date",
        "second_appeal_date",
        "commissioner_name",
        "appellant_name",
        "respondent_name",
        "public_authority",
        "department",
        "ministry",
        "cpio_name",
        "faa_name",
        "facts",
        "grounds_for_appeal",
        "rti_request_summary",
        "final_order",
        "outcome",
        "pio_learning_signal",
        "precedent_chunk",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator(
        "decision_date",
        "hearing_date",
        "rti_application_date",
        "cpio_reply_date",
        "first_appeal_date",
        "faa_order_date",
        "second_appeal_date",
    )
    @classmethod
    def _normalize_iso_date(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return text

    @field_validator("sections_invoked", mode="before")
    @classmethod
    def _normalize_sections(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = re.split(r"[,;\n]+", value)
        else:
            raw_items = list(value)

        sections: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = str(item).strip()
            text = re.sub(r"(?i)^section\s+", "", text)
            text = re.sub(r"\s+", "", text)
            text = text.replace("（", "(").replace("）", ")")
            if not text:
                continue
            if text.lower() not in seen:
                sections.append(text)
                seen.add(text.lower())
        return sections

    @field_validator("rti_sections", "exemption_sections", mode="before")
    @classmethod
    def _normalize_section_lists(cls, value) -> list[str]:
        return cls._normalize_generic_list(value, section_mode=True)

    @field_validator(
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
        mode="before",
    )
    @classmethod
    def _normalize_text_lists(cls, value) -> list[str]:
        return cls._normalize_generic_list(value, section_mode=False)

    @staticmethod
    def _normalize_generic_list(value, section_mode: bool = False) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = re.split(r"[,;\n]+", value)
        else:
            raw_items = list(value)

        items: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = str(item).strip()
            if section_mode:
                text = re.sub(r"(?i)^section\s+", "", text)
                text = re.sub(r"\s+", "", text)
            else:
                text = re.sub(r"\s+", " ", text)
            text = text.strip(" -•\t\n.")
            if not text:
                continue
            key = text.lower()
            if key not in seen:
                items.append(text)
                seen.add(key)
        return items

    @field_validator("outcome")
    @classmethod
    def _normalize_outcome(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        text = str(value).strip().upper()
        text = re.sub(r"[^A-Z]+", "_", text).strip("_")
        aliases = {
            "ALLOWED": "APPEAL_ALLOWED",
            "APPEAL_ALLOWED": "APPEAL_ALLOWED",
            "DISMISSED": "REJECTED",
            "REJECTED": "REJECTED",
            "DENIED": "REJECTED",
            "DISPOSED": "APPEAL_DISPOSED",
            "APPEAL_DISPOSED": "APPEAL_DISPOSED",
            "APPEAL_DISPOSED_NO_INTERVENTION": "APPEAL_DISPOSED",
            "NO_INTERVENTION": "APPEAL_DISPOSED",
            "NO_INTERFERENCE_REQUIRED": "APPEAL_DISPOSED",
            "PARTLY_ALLOWED": "PARTIAL",
            "PARTIALLY_ALLOWED": "PARTIAL",
            "PARTIAL": "PARTIAL",
            "PENALTY": "PENALTY",
            "SHOW_CAUSE": "PENALTY",
        }
        mapped = aliases.get(text, text)
        return mapped if mapped in VALID_OUTCOMES else None

    @field_validator("penalty_amount", mode="before")
    @classmethod
    def _normalize_penalty_amount(cls, value) -> Optional[int]:
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return max(value, 0)
        digits = re.sub(r"[^\d]", "", str(value))
        return int(digits) if digits else None

    @field_validator("key_findings", mode="before")
    @classmethod
    def _normalize_key_findings(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = re.split(r"(?:\n+|;\s+|\.\s+(?=[A-Z]))", value)
        else:
            items = list(value)

        findings: list[str] = []
        for item in items:
            text = re.sub(r"\s+", " ", str(item)).strip(" -•\t\n.")
            if not text:
                continue
            # Keep findings as bullet-sized statements, not long paragraphs.
            words = text.split()
            if len(words) > 38:
                text = " ".join(words[:38]).rstrip(",;:") + "."
            if text not in findings:
                findings.append(text)
            if len(findings) >= 5:
                break
        return findings

    @field_validator("source")
    @classmethod
    def _normalize_source(cls, value: str) -> str:
        text = str(value or "").strip().upper()
        return text if text in VALID_SOURCES else "CIC"

    @field_validator("extraction_confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
