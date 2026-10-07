"""Hybrid lexical/category/semantic retrieval with deterministic reranking."""
from dataclasses import dataclass
from app.services.query_expander import expand_query


@dataclass(frozen=True)
class RetrievedEvidence:
    source: dict
    score: float
    channels: tuple[str, ...]


class KnowledgeRetriever:
    @staticmethod
    def _is_public_official(source: dict) -> bool:
        visibility = str(source.get("visibility", "")).strip().upper()
        source_type = str(source.get("source_type", "")).strip().casefold()
        if source_type in {"internal_organizer_research", "internal_aggregated_cdp", "internal_organizer"}:
            return False
        if visibility:
            return visibility == "PUBLIC"
        return source_type in {"official", "public_official", "government", "manufacturer", "owner_manual", "toyota_official"}

    def retrieve(self, repository: object, query: str, topic: str | None = None) -> list[RetrievedEvidence]:
        list_sources = getattr(repository, "search_knowledge_sources", None)
        sources = list_sources(query=query, topic=topic, terms=expand_query(query)) if callable(list_sources) else []
        terms = tuple(term.lower() for term in expand_query(query) if len(term) > 1)
        ranked: list[RetrievedEvidence] = []
        for source in sources:
            if not self._is_public_official(source):
                continue
            haystack = " ".join(str(source.get(key, "")) for key in ("title", "content", "keywords", "topic", "category")).lower()
            exact = sum(1 for term in terms if term in haystack)
            category = 1 if topic and topic in {source.get("category"), source.get("topic")} else 0
            # Token overlap is a small local semantic proxy when vector RPC is
            # unavailable; Supabase can later replace this channel with embeddings.
            semantic = len(set(query.lower()) & set(haystack)) / max(len(set(query.lower())), 1)
            score = exact * 0.35 + category * 0.25 + semantic * 0.4 + float(source.get("priority", 0)) * .01
            channels = tuple(name for name, used in (("exact", exact), ("category", category), ("semantic", semantic > .15)) if used)
            ranked.append(RetrievedEvidence(source, score, channels))
        return sorted(ranked, key=lambda item: item.score, reverse=True)


knowledge_retriever = KnowledgeRetriever()
