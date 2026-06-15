from src.retrieval.hybrid_retriever import RetrievedChunk
from src.retrieval.reference_retriever import ReferenceRetriever


class FakeHybridRetriever:
    def search(self, query, n_results=10, filters=None, search_mode="hybrid"):
        return [
            RetrievedChunk(
                chunk_id=f"{search_mode}-1",
                case_number="CIC/AAOIN/A/2017/102333",
                source="CIC",
                chunk_type="PRECEDENT_SUMMARY",
                text="Applicant sought Airport Authority committee records. Commission found CPIO reply just and proper and pointwise.",
                decision_date="2018-04-05",
                outcome="APPEAL_DISPOSED",
                department="Airport Authority of India",
                metadata={
                    "public_authority": "Airport Authority of India",
                    "rti_sections": ["6(3)"],
                    "outcome": "APPEAL_DISPOSED",
                    "date": "2018-04-05",
                },
                rrf_score=0.9,
                rank=1,
            )
        ]


class RankingHybridRetriever:
    def search(self, query, n_results=10, filters=None, search_mode="hybrid"):
        return [
            RetrievedChunk(
                chunk_id=f"{search_mode}-request",
                case_number="CIC/REQ/A/2020/000001",
                source="CIC",
                chunk_type="RTI_REQUEST",
                text="Applicant sought committee report, proceedings, members and compliance information.",
                decision_date="2020-01-01",
                outcome="APPEAL_DISPOSED",
                public_authority="Airport Authority of India",
                metadata={
                    "case_number": "CIC/REQ/A/2020/000001",
                    "public_authority": "Airport Authority of India",
                    "outcome": "APPEAL_DISPOSED",
                    "hearing_date": "2020-01-01",
                    "reasoning_pattern": "Request facts only",
                    "pio_learning_signal": "",
                    "chunk_type": "RTI_REQUEST",
                },
                rrf_score=1.0,
                rank=1,
            ),
            RetrievedChunk(
                chunk_id=f"{search_mode}-observation",
                case_number="CIC/OBS/A/2020/000002",
                source="CIC",
                chunk_type="COMMISSION_OBSERVATION",
                text="Commission observed that pointwise reply on committee proceedings and final report was just and proper.",
                decision_date="2020-01-02",
                outcome="APPEAL_DISPOSED",
                public_authority="Airport Authority of India",
                metadata={
                    "case_number": "CIC/OBS/A/2020/000002",
                    "public_authority": "Airport Authority of India",
                    "outcome": "APPEAL_DISPOSED",
                    "hearing_date": "2020-01-02",
                    "reasoning_pattern": "Pointwise reply considered adequate",
                    "pio_learning_signal": "Pointwise replies are likely to be upheld.",
                    "chunk_type": "COMMISSION_OBSERVATION",
                },
                rrf_score=0.72,
                rank=2,
            ),
        ]


def test_reference_retriever_returns_compact_cards_with_metadata():
    retriever = ReferenceRetriever(retriever=FakeHybridRetriever())
    cards = retriever.retrieve(
        raw_text="Provide information about airport committee records and compliance status.",
        extracted_parameters={"information_type": "committee records"},
        sections=["6(3)"],
        department_context="Airport Authority of India",
        limit=3,
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.source_type == "CIC Decision"
    assert card.title_or_case_number == "CIC/AAOIN/A/2017/102333"
    assert card.public_authority == "Airport Authority of India"
    assert card.outcome == "APPEAL_DISPOSED"
    assert card.confidence_score > 0.5
    assert "Applicant sought" in card.why_relevant
    assert "legal chunk type" not in card.why_relevant
    assert "relevance_reason" in card.metadata


def test_committee_queries_rank_commission_reasoning_above_raw_request():
    retriever = ReferenceRetriever(retriever=RankingHybridRetriever())
    cards = retriever.retrieve(
        raw_text="Please provide committee report, proceedings, members, and compliance status.",
        extracted_parameters={"information_type": "committee report"},
        department_context="Airport Authority of India",
        limit=2,
    )

    assert cards[0].title_or_case_number == "CIC/OBS/A/2020/000002"
    assert cards[0].metadata["chunk_type"] == "COMMISSION_OBSERVATION"
    assert cards[0].metadata["hearing_date"] == "2020-01-02"
    assert "Pointwise" in cards[0].metadata["reasoning_pattern"]
    assert "Commission reasoning" in cards[0].why_relevant
