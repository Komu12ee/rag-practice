from pathlib import Path

from src.pipeline.legal_document_parser import LegalDocumentParser


def test_sample_cic_pdf_text_extracts_rich_fields():
    text_path = Path("data/extracted/cic/CIC_AAOIN_A_2017_102333.txt")
    parsed = LegalDocumentParser().parse_text(
        text_path.read_text(encoding="utf-8", errors="replace"),
        source_file=str(text_path),
    )

    assert parsed.case_number == "CIC/AAOIN/A/2017/102333"
    assert parsed.commission == "Central Information Commission"
    assert parsed.appellant_name == "Sudesh Raghunath Gaikwad"
    assert "Airport Authority of India" in (parsed.public_authority or "")
    assert parsed.rti_application_date == "2016-03-10"
    assert parsed.cpio_reply_date == "2016-04-20"
    assert parsed.first_appeal_date == "2016-04-18"
    assert parsed.second_appeal_date == "2016-07-11"
    assert parsed.hearing_date == "2018-04-05"
    assert parsed.information_requested
    assert any("High Court" in ref for ref in parsed.court_references)
    assert parsed.commission_observations
    assert parsed.outcome == "APPEAL_DISPOSED"
    assert any("Pointwise reply" in item or "No Commission interference" in item for item in parsed.reasoning_pattern)
    assert parsed.entities_person
    assert parsed.entities_authority
    assert parsed.entities_location
    assert parsed.precedent_chunk
    assert "just and proper" in parsed.precedent_chunk.lower()


def test_parser_handles_missing_respondent_without_crashing():
    text = """
Central Information Commission
File No: CIC/TEST/A/2020/000001

Facts
The appellant sought information about public records.

Order
The appeal is disposed of.
"""
    parsed = LegalDocumentParser().parse_text(text)

    assert parsed.case_number == "CIC/TEST/A/2020/000001"
    assert parsed.respondent_name is None
    assert parsed.cpio_name is None
    assert parsed.source == "CIC"


def test_cpio_name_accepts_none_inputs():
    assert LegalDocumentParser._cpio_name(None, None) is None
