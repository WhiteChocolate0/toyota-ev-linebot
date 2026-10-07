"""Retrieval-only query expansion. The original user text is never changed."""

EXPANSIONS = {
    "電車": ("ev", "bev", "純電車", "電動車"), "電動車": ("ev", "bev", "純電車"),
    "油電": ("hev", "hybrid", "油電車"), "充電樁": ("家充", "ac charging", "220v", "充電"),
    "保值": ("resale", "residual", "殘值", "二手"), "電池": ("動力電池", "battery", "保固"),
}


def expand_query(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    terms = {text, *[word for word in text.replace("？", " ").replace("?", " ").split() if word]}
    for phrase, aliases in EXPANSIONS.items():
        if phrase in lowered:
            terms.update(aliases)
    return tuple(terms)
