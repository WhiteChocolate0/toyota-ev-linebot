"""Compose concise answers from evidence; never paste source bodies verbatim."""
from app.services.evidence_validator import EvidenceAssessment

def compose_answer(question: str, fallback: str, assessment: EvidenceAssessment) -> tuple[str, dict | None]:
    if assessment.status == "INSUFFICIENT":
        if any(word in question for word in ("殘值", "二手", "五年後", "保值")):
            return "目前沒有可靠官方資料能直接估定未來售價。我可以改用保守／基準／樂觀情境試算，但那會是估計，不是官方保證。", None
        return fallback, None
    source = assessment.evidence.source if assessment.evidence else None
    # The approved route template is already a reviewed concise paraphrase.
    # Evidence is used for grounding/citation, never returned as a pasted blob.
    caveat = "此資料有期限，建議再次確認最新公告。" if source and source.get("valid_until") else ""
    return (fallback + ("\n\n" + caveat if caveat else "")), source
