"""Shared parsing and normalization for one-time campaign handoff messages."""
from __future__ import annotations

from typing import TypedDict
from urllib.parse import parse_qs, unquote, urlsplit
import re

_RAW_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class CampaignHandoffResult(TypedDict, total=False):
    status: str
    quiz_result_id: str
    persona_key: str
    ability_scores: dict[str, int | float]
    result_summary: dict[str, str]


def parse_campaign_handoff_token(value: object) -> str | None:
    """Extract one raw token; return empty string for a malformed token parameter."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 512:
        return None
    query = urlsplit(candidate).query if candidate.startswith("http") else candidate.lstrip("?")
    params = parse_qs(unquote(query), keep_blank_values=True, strict_parsing=False)
    if "campaign_token" not in params:
        return None
    tokens = params.get("campaign_token", [])
    if len(tokens) != 1 or not _RAW_TOKEN.fullmatch(tokens[0]):
        return ""
    return tokens[0]


def normalize_campaign_summary(value: object) -> dict[str, str]:
    """Keep only short profile fields used to phrase the immediate opener."""
    if not isinstance(value, dict):
        return {}
    if isinstance(value.get("persona_name"), str) or isinstance(value.get("conversation_hint"), str):
        return {
            key: value[key].strip()[:limit]
            for key, limit in (("persona_name", 80), ("conversation_hint", 180))
            if isinstance(value.get(key), str) and value[key].strip()
        }
    profile = value.get("profile")
    if not isinstance(profile, dict):
        return {}
    normalized: dict[str, str] = {}
    for source, target, limit in (("name", "persona_name", 80), ("communicationTip", "conversation_hint", 180)):
        item = profile.get(source)
        if isinstance(item, str) and item.strip():
            normalized[target] = item.strip()[:limit]
    return normalized


def normalize_campaign_rpc_result(value: object) -> CampaignHandoffResult:
    """Translate the deployed RPC's legacy keys/statuses to app contract."""
    if not isinstance(value, dict):
        return {"status": "HANDOFF_UNAVAILABLE"}
    raw_status = str(value.get("status", "")).casefold()
    status_map = {
        "ok": "SUCCESS",
        "success": "SUCCESS",
        "invalid": "TOKEN_NOT_FOUND",
        "token_not_found": "TOKEN_NOT_FOUND",
        "expired": "TOKEN_EXPIRED",
        "token_expired": "TOKEN_EXPIRED",
        "consumed": "TOKEN_ALREADY_CONSUMED",
        "token_already_consumed": "TOKEN_ALREADY_CONSUMED",
        "result_not_found": "RESULT_NOT_FOUND",
    }
    status = status_map.get(raw_status, "HANDOFF_UNAVAILABLE")
    result: CampaignHandoffResult = {"status": status}
    if status in {"SUCCESS", "TOKEN_ALREADY_CONSUMED"}:
        result_id = value.get("quiz_result_id") or value.get("campaign_result_id")
        if isinstance(result_id, str) and result_id:
            result["quiz_result_id"] = result_id
    if status == "SUCCESS":
        persona = value.get("persona_key")
        if isinstance(persona, str):
            result["persona_key"] = persona[:80]
        scores = value.get("ability_scores") or value.get("ability_scores_json")
        if isinstance(scores, dict):
            result["ability_scores"] = {
                str(key)[:40]: number for key, number in scores.items()
                if isinstance(key, str) and isinstance(number, (int, float)) and not isinstance(number, bool)
            }
        result["result_summary"] = normalize_campaign_summary(value.get("result_summary"))
    return result
