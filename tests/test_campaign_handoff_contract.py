from urllib.parse import quote

from app.services.campaign_handoff import (
    normalize_campaign_rpc_result,
    normalize_campaign_summary,
    parse_campaign_handoff_token,
)


def test_campaign_token_parser_accepts_message_and_postback_contract():
    token = "A" * 43
    assert parse_campaign_handoff_token(f"campaign_token={token}") == token
    assert parse_campaign_handoff_token(f"?campaign_token={token}&action=handoff") == token
    assert parse_campaign_handoff_token(f"https://line.me/R/oaMessage/%40bot/?{quote(f'campaign_token={token}')}") == token


def test_campaign_token_parser_rejects_absent_malformed_or_ambiguous_parameters():
    assert parse_campaign_handoff_token("hello") is None
    assert parse_campaign_handoff_token("campaign_token=short") == ""
    assert parse_campaign_handoff_token(f"campaign_token={'A' * 43}&campaign_token={'B' * 43}") == ""
    assert parse_campaign_handoff_token(None) is None


def test_campaign_rpc_payload_maps_to_application_contract_and_minimal_summary():
    result = normalize_campaign_rpc_result({
        "status": "ok",
        "campaign_result_id": "result-123",
        "persona_key": "money",
        "ability_scores_json": {"money": 8, "unexpected": "not-a-score"},
        "result_summary": {"primary": "money", "profile": {
            "name": "成本規劃型", "communicationTip": "先討論預算", "doList": ["不要保留整份資料"],
        }},
    })
    assert result == {
        "status": "SUCCESS", "quiz_result_id": "result-123", "persona_key": "money",
        "ability_scores": {"money": 8},
        "result_summary": {"persona_name": "成本規劃型", "conversation_hint": "先討論預算"},
    }
    assert "doList" not in str(result)


def test_normalized_campaign_summary_is_idempotent():
    summary = {"persona_name": "成本規劃型", "conversation_hint": "先討論預算", "full_profile": "drop"}
    assert normalize_campaign_summary(normalize_campaign_summary(summary)) == {
        "persona_name": "成本規劃型", "conversation_hint": "先討論預算",
    }
