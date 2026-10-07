import hashlib
from types import SimpleNamespace

from app.services.linebot_repository import LinebotRepository


class FakeRPC:
    def __init__(self, data=None):
        self.params = None
        self.data = data or {"status": "ok"}

    def rpc(self, _name, params):
        self.params = params
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


def test_campaign_repository_sends_token_hash_not_bearer_token():
    rpc = FakeRPC({
        "status": "ok",
        "campaign_result_id": "quiz-result-1",
        "persona_key": "money",
        "ability_scores_json": {"money": 8},
        "result_summary": {"profile": {"name": "省錢規劃型", "communicationTip": "先比較成本", "private": "drop"}},
    })
    repository = LinebotRepository.__new__(LinebotRepository)
    repository._client = SimpleNamespace(_client=rpc)

    result = repository.consume_campaign_token("opaque-bearer-token", "line-user-id")

    assert result == {
        "status": "SUCCESS",
        "quiz_result_id": "quiz-result-1",
        "persona_key": "money",
        "ability_scores": {"money": 8},
        "result_summary": {"persona_name": "省錢規劃型", "conversation_hint": "先比較成本"},
    }
    assert rpc.params["p_token_hash"] == hashlib.sha256(b"opaque-bearer-token").hexdigest()
    assert rpc.params["p_token_hash"] != "opaque-bearer-token"
    assert set(rpc.params) == {"p_token_hash"}


def test_repository_maps_rpc_error_codes_to_canonical_contract():
    for rpc_status, expected in (
        ("invalid", "TOKEN_NOT_FOUND"),
        ("expired", "TOKEN_EXPIRED"),
        ("consumed", "TOKEN_ALREADY_CONSUMED"),
        ("result_not_found", "RESULT_NOT_FOUND"),
    ):
        repository = LinebotRepository.__new__(LinebotRepository)
        repository._client = SimpleNamespace(_client=FakeRPC({"status": rpc_status}))
        assert repository.consume_campaign_token("opaque", "user")["status"] == expected


def test_consumed_rpc_result_normalizes_result_id_for_same_context_check():
    repository = LinebotRepository.__new__(LinebotRepository)
    repository._client = SimpleNamespace(_client=FakeRPC({"status": "consumed", "campaign_result_id": "result-2"}))
    assert repository.consume_campaign_token("opaque", "user") == {
        "status": "TOKEN_ALREADY_CONSUMED", "quiz_result_id": "result-2"
    }
