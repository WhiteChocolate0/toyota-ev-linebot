"""Deterministic, seedable wording variants; no random CI behaviour."""

from __future__ import annotations

import random


def variants(text: str, seed: int = 20260928) -> list[str]:
    rng = random.Random(seed)
    compact = text.replace("？", "").replace("?", "")
    candidates = [compact, compact.lower(), "  " + compact + "  ", compact.replace("多少錢", "價格呢"), compact.replace("車價", "售價")]
    rng.shuffle(candidates)
    return list(dict.fromkeys(candidate for candidate in candidates if candidate.strip()))
