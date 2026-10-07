"""Assertions for conversational quality, not just routing correctness."""

from __future__ import annotations

import re
from dataclasses import dataclass


INTERNAL_TERMS = re.compile(
    r"\b(?:RAG|L[0-3]|intent|flow|scope|pending_field|classifier|"
    r"context_json|webhook|Supabase|exception|traceback)\b", re.I
)
GENERIC_FALLBACKS = (
    "我不太確定你的問題",
    "請換個方式問",
    "無法回答這個問題",
    "系統忙碌",
)


@dataclass(frozen=True)
class UXFailure:
    assertion: str
    detail: str


def evaluate(*, reply: str, previous_replies: list[str], must_include: list[str],
             must_not_include: list[str], should_reply: bool,
             should_preserve_flow: bool, flow_before: str | None,
             flow_after: str | None) -> list[UXFailure]:
    """Return every user-facing quality failure for one conversation turn."""
    failures: list[UXFailure] = []
    if should_reply and not reply:
        failures.append(UXFailure("answers_user_question", "expected a reply, received silence"))
    if not should_reply and reply:
        failures.append(UXFailure("answers_user_question", "expected silence, received a reply"))
    if reply:
        for text in must_include:
            if text not in reply:
                failures.append(UXFailure("answers_user_question", f"missing required user-facing text: {text}"))
        for text in must_not_include:
            if text.casefold() in reply.casefold():
                failures.append(UXFailure("answers_user_question", f"contains forbidden text: {text}"))
        if INTERNAL_TERMS.search(reply):
            failures.append(UXFailure("does_not_expose_internal_terms", "reply contains an internal implementation term"))
        if any(fallback in reply for fallback in GENERIC_FALLBACKS) and must_include:
            failures.append(UXFailure("does_not_use_generic_fallback_when_answerable", "generic fallback used for answerable question"))
        # A full identical response twice in a row is generally a lost turn, not a natural continuation.
        if previous_replies and reply.strip() == previous_replies[-1].strip() and len(reply.strip()) > 20:
            failures.append(UXFailure("does_not_repeat_known_info", "same full reply repeated"))
        if len(reply) > 900:
            failures.append(UXFailure("concise_enough", f"reply has {len(reply)} characters (limit 900)"))
        if re.search(r"(?:^|\n)\s*(?:\{|\[|Traceback|AssertionError)", reply):
            failures.append(UXFailure("natural_language", "reply looks like a diagnostic payload"))
    if should_preserve_flow and flow_before and flow_after != flow_before:
        failures.append(UXFailure("does_not_switch_flow_without_reason", f"flow changed from {flow_before} to {flow_after}"))
        failures.append(UXFailure("preserves_context", "active flow was not preserved during side query"))
    return failures
