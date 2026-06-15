"""
Citation-aware response templates for RTI analysis results.

This module extends the existing response generation flow by turning an
RTIAnalysisResult into three outputs:
1. Internal note for PIO review.
2. Structured PIO recommendation.
3. Appellant-facing draft RTI reply.

Install requirements:
    pip install pydantic

Run embedded tests:
    python src/generation/response_templates.py --test
"""

from __future__ import annotations

import argparse
import re
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from engine.rti_analysis_engine import ExemptionRisk, RTIAnalysisResult, SimilarCase


INTERNAL_NOTE_TEMPLATE = """INTERNAL NOTE - PIO USE ONLY

Department identified:
{department}

Similar CIC/SIC cases:
{similar_cases}

Exemption risks:
{exemption_risks}

Recommended action:
{recommended_action}

Confidence level:
{confidence_level}
"""

PIO_RECOMMENDATION_TEMPLATE = """PIO RECOMMENDATION

Recommended response type: {response_type}
Sections to invoke: {sections_to_invoke}
Deadline reminder: {deadline_reminder}
Key legal basis: {key_legal_basis}
Risk assessment: {risk_assessment}
"""

DRAFT_RTI_REPLY_TEMPLATE = """[Letterhead]
Date: {date}
To: {appellant_name}

Subject: Reply to RTI Application dated {rti_date}

Dear Applicant,

With reference to your RTI application regarding {rti_subject}, the following
information is provided:

{response_body}

{exemption_block}

This decision is based on CIC precedent in {case_citations}.

You may appeal this decision within 30 days to the First Appellate Authority.

{signature_block}
"""

DEFAULT_SIGNATURE_BLOCK = """Public Information Officer
Chhattisgarh Infotech Promotion Society (CHiPS)
Government of Chhattisgarh"""

RESPONSE_TYPES = {"PROVIDE", "DENY", "PARTIAL", "SEEK_CLARIFICATION"}
RISK_LEVELS = {"HIGH", "MEDIUM", "LOW"}


class PIORecommendation(BaseModel):
    """Structured recommendation for the PIO."""

    recommended_response_type: str = Field(pattern=r"^(PROVIDE|DENY|PARTIAL|SEEK_CLARIFICATION)$")
    sections_to_invoke: list[str] = Field(default_factory=list)
    deadline_reminder: str
    key_legal_basis: str
    risk_assessment: str = Field(pattern=r"^(HIGH|MEDIUM|LOW)$")


class GeneratedResponseSet(BaseModel):
    """All response outputs produced from one RTIAnalysisResult."""

    internal_note: str
    pio_recommendation: PIORecommendation
    draft_rti_reply: str

    @field_validator("internal_note", "draft_rti_reply")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return str(value or "").strip()


class ResponseGenerator:
    """Generate citation-aware response outputs from RTIAnalysisResult."""

    def __init__(
        self,
        default_appellant_name: str = "The Applicant",
        signature_block: str = DEFAULT_SIGNATURE_BLOCK,
    ):
        self.default_appellant_name = default_appellant_name
        self.signature_block = signature_block

    def generate_internal_note(self, analysis: RTIAnalysisResult) -> str:
        """Create a PIO-only internal note. Do not send this to the appellant."""
        similar_cases = self._format_similar_cases(analysis.similar_cases)
        exemption_risks = self._format_exemption_risks(analysis.exemption_risks)
        confidence_level = self._confidence_label(analysis.recommendation_confidence)

        return INTERNAL_NOTE_TEMPLATE.format(
            department=analysis.department or "Unknown",
            similar_cases=similar_cases,
            exemption_risks=exemption_risks,
            recommended_action=analysis.recommendation or "Manual review required.",
            confidence_level=f"{confidence_level} ({analysis.recommendation_confidence:.2f})",
        ).strip()

    def generate_pio_recommendation(
        self,
        analysis: RTIAnalysisResult,
        rti_date: Optional[str] = None,
    ) -> PIORecommendation:
        """Create structured PIO recommendation fields."""
        response_type = self._recommended_response_type(analysis)
        sections = self._sections_to_invoke(analysis)
        deadline = self._deadline_reminder(rti_date)
        legal_basis = self._key_legal_basis(analysis)
        risk = self._adverse_order_risk(analysis, response_type)

        return PIORecommendation(
            recommended_response_type=response_type,
            sections_to_invoke=sections,
            deadline_reminder=deadline,
            key_legal_basis=legal_basis,
            risk_assessment=risk,
        )

    def generate_draft_rti_reply(
        self,
        analysis: RTIAnalysisResult,
        appellant_name: Optional[str] = None,
        rti_date: Optional[str] = None,
        rti_subject: Optional[str] = None,
        reply_date: Optional[str] = None,
    ) -> str:
        """Create a formal appellant-facing RTI reply draft."""
        recommendation = self.generate_pio_recommendation(analysis, rti_date)
        citations = self._case_citations(analysis)
        response_body = self._response_body(analysis, recommendation)
        exemption_block = self._exemption_block(analysis, recommendation)

        return DRAFT_RTI_REPLY_TEMPLATE.format(
            date=reply_date or date.today().strftime("%d/%m/%Y"),
            appellant_name=appellant_name or self.default_appellant_name,
            rti_date=rti_date or "the date mentioned in the application",
            rti_subject=rti_subject or self._subject_from_analysis(analysis),
            response_body=response_body,
            exemption_block=exemption_block,
            case_citations=citations,
            signature_block=self.signature_block,
        ).strip()

    def generate_all(
        self,
        analysis: RTIAnalysisResult,
        appellant_name: Optional[str] = None,
        rti_date: Optional[str] = None,
        rti_subject: Optional[str] = None,
        reply_date: Optional[str] = None,
    ) -> GeneratedResponseSet:
        """Generate all three required outputs from one analysis result."""
        return GeneratedResponseSet(
            internal_note=self.generate_internal_note(analysis),
            pio_recommendation=self.generate_pio_recommendation(analysis, rti_date),
            draft_rti_reply=self.generate_draft_rti_reply(
                analysis=analysis,
                appellant_name=appellant_name,
                rti_date=rti_date,
                rti_subject=rti_subject,
                reply_date=reply_date,
            ),
        )

    @staticmethod
    def _format_similar_cases(cases: list[SimilarCase]) -> str:
        if not cases:
            return "- No similar CIC/SIC decisions were retrieved."
        return "\n".join(
            f"- {case.case_number} | Date: {case.decision_date or 'N/A'} | "
            f"Outcome: {case.outcome or 'N/A'} | Finding: {case.key_finding or 'N/A'}"
            for case in cases
        )

    @staticmethod
    def _format_exemption_risks(risks: list[ExemptionRisk]) -> str:
        if not risks:
            return "- No exemption risk was identified from retrieved CIC/SIC decisions."
        return "\n".join(
            f"- Section {risk.section}: {risk.risk_level} risk. "
            f"{risk.reasoning} [{risk.cic_precedent}]"
            for risk in risks
        )

    @staticmethod
    def _recommended_response_type(analysis: RTIAnalysisResult) -> str:
        text = f"{analysis.recommendation} {analysis.draft_response_hint}".lower()
        if not analysis.similar_cases and analysis.recommendation_confidence < 0.35:
            return "SEEK_CLARIFICATION"
        if any(word in text for word in ("deny", "reject", "refuse", "withhold")):
            return "DENY"
        if analysis.exemption_risks:
            return "PARTIAL"
        return "PROVIDE"

    @staticmethod
    def _sections_to_invoke(analysis: RTIAnalysisResult) -> list[str]:
        sections: list[str] = []
        for risk in analysis.exemption_risks:
            section = ResponseGenerator._section_label(risk.section)
            if section not in sections:
                sections.append(section)
        for section in analysis.detected_sections:
            labelled = ResponseGenerator._section_label(section)
            if labelled not in sections and any(labelled.endswith(r.section) for r in analysis.exemption_risks):
                sections.append(labelled)
        return sections

    @staticmethod
    def _deadline_reminder(rti_date: Optional[str]) -> str:
        parsed = ResponseGenerator._parse_date(rti_date)
        if parsed:
            due = parsed + timedelta(days=30)
            return (
                f"Reply must be issued within 30 days from RTI date "
                f"({parsed.strftime('%d/%m/%Y')}), i.e. by {due.strftime('%d/%m/%Y')}."
            )
        return "Reply must be issued within 30 days from the RTI application date under Section 7(1)."

    @staticmethod
    def _key_legal_basis(analysis: RTIAnalysisResult) -> str:
        citations = ResponseGenerator._case_citations(analysis)
        if analysis.exemption_risks:
            risk_text = "; ".join(
                f"Section {risk.section} considered with precedent {risk.cic_precedent}"
                for risk in analysis.exemption_risks
            )
            return f"{risk_text}. Cited cases: {citations}."
        return f"No denial exemption was recommended. Cited cases: {citations}."

    @staticmethod
    def _adverse_order_risk(analysis: RTIAnalysisResult, response_type: str) -> str:
        if response_type == "SEEK_CLARIFICATION":
            return "HIGH"
        if analysis.recommendation_confidence < 0.45:
            return "HIGH"
        if any(risk.risk_level == "HIGH" for risk in analysis.exemption_risks):
            return "HIGH"
        if analysis.recommendation_confidence < 0.70 or response_type in {"DENY", "PARTIAL"}:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _response_body(analysis: RTIAnalysisResult, recommendation: PIORecommendation) -> str:
        if recommendation.recommended_response_type == "PROVIDE":
            return (
                "The request has been examined. Based on the available analysis and retrieved CIC/SIC "
                "decisions, the information may be provided if it is held by this public authority and "
                "no exempt material is found in the records."
            )
        if recommendation.recommended_response_type == "DENY":
            return (
                "The request has been examined. The requested information, to the extent covered by the "
                "sections listed below, is not recommended for disclosure because the cited CIC/SIC "
                "precedents support application of the relevant exemption."
            )
        if recommendation.recommended_response_type == "PARTIAL":
            return (
                "The request has been examined. Disclosable information may be provided after severing "
                "or redacting exempt portions under Section 10 of the RTI Act, 2005. The legal basis for "
                "withholding/redacting the exempt portions is stated below."
            )
        return (
            "The request requires clarification or additional record verification before a final response "
            "is issued. The applicant may be asked to clarify the exact records sought, if necessary."
        )

    @staticmethod
    def _exemption_block(analysis: RTIAnalysisResult, recommendation: PIORecommendation) -> str:
        if recommendation.recommended_response_type == "PROVIDE" or not analysis.exemption_risks:
            return "No exemption is invoked in this draft reply."

        details = "\n".join(
            f"- Section {risk.section}: {risk.reasoning} [{risk.cic_precedent}]"
            for risk in analysis.exemption_risks
        )
        return (
            "The following information is exempted under:\n"
            f"{details}"
        )

    @staticmethod
    def _case_citations(analysis: RTIAnalysisResult) -> str:
        citations = ResponseGenerator._unique(analysis.sources_cited)
        if not citations:
            citations = ResponseGenerator._unique(case.case_number for case in analysis.similar_cases)
        return ", ".join(citations) if citations else "no retrieved CIC/SIC case citation"

    @staticmethod
    def _subject_from_analysis(analysis: RTIAnalysisResult) -> str:
        if analysis.detected_sections:
            return f"information request involving RTI Act Section(s) {', '.join(analysis.detected_sections)}"
        if analysis.department:
            return f"information request concerning {analysis.department}"
        return "the requested information"

    @staticmethod
    def _confidence_label(confidence: float) -> str:
        if confidence >= 0.75:
            return "HIGH"
        if confidence >= 0.45:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _section_label(section: str) -> str:
        text = str(section or "").strip()
        if not text:
            return ""
        return text if text.lower().startswith("section ") else f"Section {text}"

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

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


class TestResponseGenerator(unittest.TestCase):
    def _analysis(self) -> RTIAnalysisResult:
        return RTIAnalysisResult(
            department="Revenue Department",
            detected_sections=["8(1)(j)"],
            exemption_risks=[
                ExemptionRisk(
                    section="8(1)(j)",
                    risk_level="MEDIUM",
                    reasoning="Personal details in file notings should be redacted before disclosure.",
                    cic_precedent="CIC/TEST/A/2024/000001",
                )
            ],
            similar_cases=[
                SimilarCase(
                    case_number="CIC/TEST/A/2024/000001",
                    decision_date="2024-02-01",
                    outcome="PARTIAL",
                    similarity_score=0.94,
                    key_finding="File notings may be disclosed after redaction of personal information.",
                )
            ],
            relevant_circulars=[],
            recommendation="Provide file notings after redacting personal information.",
            recommendation_confidence=0.78,
            draft_response_hint="Use Section 10 severance and cite the CIC precedent.",
            sources_cited=["CIC/TEST/A/2024/000001"],
            analysis_type="exemption_check",
            processing_time_seconds=1.2,
        )

    def test_three_outputs_generated_with_citations(self):
        outputs = ResponseGenerator().generate_all(
            analysis=self._analysis(),
            appellant_name="Shri Test Applicant",
            rti_date="2024-05-01",
            rti_subject="file notings",
            reply_date="15/05/2024",
        )

        self.assertIn("INTERNAL NOTE", outputs.internal_note)
        self.assertEqual(outputs.pio_recommendation.recommended_response_type, "PARTIAL")
        self.assertIn("30 days", outputs.pio_recommendation.deadline_reminder)
        self.assertIn("MEDIUM", outputs.pio_recommendation.risk_assessment)
        self.assertIn("CIC/TEST/A/2024/000001", outputs.draft_rti_reply)
        self.assertIn("You may appeal this decision within 30 days", outputs.draft_rti_reply)
        self.assertNotIn("INTERNAL NOTE", outputs.draft_rti_reply)


def _run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestResponseGenerator)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate citation-aware RTI response outputs.")
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
