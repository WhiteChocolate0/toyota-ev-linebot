"""Normalised MVP triggers for utility flows."""

import re


def normalize_intent_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", text).lower()
    return normalized.replace("五年", "5年")


def is_cost_calculator_trigger(text: str) -> bool:
    normalized = normalize_intent_text(text)
    calculator_words = ("試算", "計算", "估算")
    if "成本" in normalized and any(word in normalized for word in calculator_words):
        return True
    if "算給爸媽看" in normalized:
        return True
    return any(phrase in normalized for phrase in ("幫我算", "幫忙算")) and any(
        word in normalized for word in ("成本", "油費", "電費")
    )


def has_explicit_cost_period(text: str) -> bool:
    normalized = normalize_intent_text(text)
    return bool(re.search(r"(?:\d+|[一二三四五六七八九十]+)年", normalized))
