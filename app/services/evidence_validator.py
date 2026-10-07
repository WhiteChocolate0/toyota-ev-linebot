"""Evidence sufficiency gates: retrieval is not permission to invent facts."""
from dataclasses import dataclass
from typing import Literal
from app.services.knowledge_retriever import RetrievedEvidence

EvidenceStatus = Literal["STRONG", "PARTIAL", "INSUFFICIENT"]

@dataclass(frozen=True)
class EvidenceAssessment:
    status: EvidenceStatus
    evidence: RetrievedEvidence | None

def assess_evidence(results: list[RetrievedEvidence]) -> EvidenceAssessment:
    if not results: return EvidenceAssessment("INSUFFICIENT", None)
    best = results[0]
    if best.score >= .55 and {"exact", "category"} & set(best.channels): return EvidenceAssessment("STRONG", best)
    if best.score >= .28: return EvidenceAssessment("PARTIAL", best)
    return EvidenceAssessment("INSUFFICIENT", None)
