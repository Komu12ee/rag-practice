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
    assert "legal chunk type" in card.why_relevant
