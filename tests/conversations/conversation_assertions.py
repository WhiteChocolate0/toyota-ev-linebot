"""Deterministic conversation UX assertions and failure classification."""

from __future__ import annotations

import re

from .ux_assertions import UXFailure, evaluate

FAILURE_TYPE_BY_ASSERTION = {
    "unexpected_intent": "INTENT", "unexpected_flow": "FLOW",
    "preserves_context": "CONTEXT", "does_not_switch_flow_without_reason": "FLOW",
    "does_not_answer_unrelated_group_chat": "GROUP",
    "does_not_ask_for_known_slot": "DATA",
    "does_not_use_generic_fallback_when_answerable": "COPY",
    "does_not_expose_internal_terms": "PRIVACY",
    "answers_user_question": "COPY", "does_not_repeat_known_info": "COPY",
    "concise_enough": "COPY", "natural_language": "COPY",
}
GENERIC_FALLBACK_PATTERNS = (
    "這題跟 EV／TOYOTA 有關", "你比較想知道的是", "可以幫你一起拆解",
)
INTERNAL_LEAK_PATTERN = re.compile(
    r"(?:T\d{2}:|\+00:00|active_topic|VEHICLE_PRICE|INPUT_MILEAGE|UNKNOWN_RELEVANT|\bnull\b)", re.I
)


def failure_type(assertion: str) -> str:
    return FAILURE_TYPE_BY_ASSERTION.get(assertion, "UI")


def assert_no_generic_fallback(reply: str, *, answerable: bool) -> list[UXFailure]:
    if answerable and any(pattern in reply for pattern in GENERIC_FALLBACK_PATTERNS):
        return [UXFailure("does_not_use_generic_fallback_when_answerable", "generic fallback used although fixture has an answer")]
    return []


def assert_no_internal_data_leak(reply: str) -> list[UXFailure]:
    if INTERNAL_LEAK_PATTERN.search(reply):
        return [UXFailure("does_not_expose_internal_terms", "internal timestamp, enum, or null leaked to user")]
    return []
