"""Normalize LINE text before any intent, keyword, or knowledge lookup."""

from dataclasses import dataclass
import re

# Longest match wins: the brand phrase must be protected before the EV word
# 「電車」is ever considered by a downstream keyword classifier.
BOT_ALIASES = ("@電車解惑所", "電車解惑所", "解惑所")
_ALIAS_PATTERN = re.compile("|".join(re.escape(alias) for alias in BOT_ALIASES))
_INVOCATION_PATTERN = re.compile(r"^(?:欸|喂|嗨|你好)?\s*(?:在嗎|在不在|在嗎\?|在嗎？|在不在\?|在不在？)$")


@dataclass(frozen=True)
class NormalizedMessage:
    text: str
    is_bot_reference: bool = False
    is_bot_invocation: bool = False


def normalize_bot_reference(message: str) -> NormalizedMessage:
    """Remove textual LINE mentions and bot aliases without retaining raw chat.

    LINE's rich mention metadata is not required for the common text forms;
    ``@電車解惑所`` is treated as a mention span.  Aliases are removed before
    downstream keyword matching, so a reference cannot become an EV query.
    """
    original = message.strip()
    cleaned = _ALIAS_PATTERN.sub(" ", original)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\n，,：:！!。")
    if not cleaned:
        # A bare alias is an intentional call for help, not an EV keyword.
        return NormalizedMessage("", is_bot_reference=bool(original), is_bot_invocation=bool(original))
    if _INVOCATION_PATTERN.fullmatch(cleaned):
        return NormalizedMessage("", is_bot_reference=True, is_bot_invocation=True)
    return NormalizedMessage(cleaned, is_bot_reference=cleaned != original)
