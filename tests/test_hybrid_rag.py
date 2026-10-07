from app.services.answer_composer import compose_answer
from app.services.evidence_validator import assess_evidence
from app.services.knowledge_retriever import knowledge_retriever
from app.services.query_expander import expand_query


class Repository:
    def search_knowledge_sources(self, **_kwargs):
        return [{"id": "battery", "category": "BATTERY", "topic": "BATTERY", "source_type": "official", "title": "bZ4X 動力電池容量保證", "content": "電池八年保固與容量條件。", "keywords": ["電池", "8年", "保固"], "priority": 100, "url": "https://example.com"}]


def test_hybrid_retrieval_expands_and_reranks_battery_question() -> None:
    assert "保固" in expand_query("電池八年後是不是就要換？")
    results = knowledge_retriever.retrieve(Repository(), "電池八年後是不是就要換？", "BATTERY")
    assert results and "exact" in results[0].channels
    assert assess_evidence(results).status == "STRONG"


def test_insufficient_resale_evidence_never_invents_price() -> None:
    answer, source = compose_answer("bZ4X 五年後一定剩多少殘值？", "fallback", assess_evidence([]))
    assert source is None and "不是官方保證" in answer
