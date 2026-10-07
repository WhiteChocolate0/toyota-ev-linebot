import json

from app.services.persona_rewriter import PersonaRewriter


class FakeResponse:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"reply": self._reply})}]}}]}


def test_rewriter_returns_approved_ai_wording() -> None:
    rewriter = PersonaRewriter(api_key="test", post=lambda *args, **kwargs: FakeResponse("正在聊 RAV4 跟 bZ4X 嗎？要不要我陪大家從日常用車和充電方式一起比較看看？"))
    result = rewriter.rewrite_vehicle_reply(
        fallback="fallback", message_text="RAV4 跟 bZ4X 怎麼比較？", source_type="group", model_names=("RAV4", "bZ4X")
    )
    assert result.startswith("正在聊 RAV4")


def test_rewriter_falls_back_when_ai_returns_an_unverified_number() -> None:
    rewriter = PersonaRewriter(api_key="test", post=lambda *args, **kwargs: FakeResponse("RAV4 的 5 年成本一定更低，要不要我直接算給你看？"))
    result = rewriter.rewrite_vehicle_reply(
        fallback="安全回覆", message_text="RAV4 跟 bZ4X", source_type="group", model_names=("RAV4",)
    )
    assert result == "安全回覆"


def test_rewriter_allows_the_preapproved_eight_year_calculator_phrase() -> None:
    rewriter = PersonaRewriter(api_key="test", post=lambda *args, **kwargs: FakeResponse("正在聊 RAV4 跟 bZ4X 嗎？要不要我陪大家用 8 年能源成本一起比較看看？"))
    result = rewriter.rewrite_vehicle_reply(
        fallback="安全回覆", message_text="RAV4 跟 bZ4X", source_type="group", model_names=("RAV4", "bZ4X")
    )
    assert "8 年能源成本" in result


def test_rewriter_without_key_uses_fallback_without_a_network_call() -> None:
    rewriter = PersonaRewriter(api_key="", post=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    result = rewriter.rewrite_vehicle_reply(
        fallback="安全回覆", message_text="RAV4", source_type="user", model_names=("RAV4",)
    )
    assert result == "安全回覆"
