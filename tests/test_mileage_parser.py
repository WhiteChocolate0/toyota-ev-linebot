import json

from app.services.mileage_parser import MileageParser


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
    def raise_for_status(self) -> None:
        pass
    def json(self) -> dict:
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(self.payload)}]}}]}


def test_parser_accepts_model_converted_weekly_mileage() -> None:
    parser = MileageParser(api_key="test", post=lambda *args, **kwargs: FakeResponse({"status": "success", "monthly_mileage": 216.5, "interpretation": "每週 50 公里×4.33", "reply": "我先以每月約 217 公里計算。"}))
    result = parser.parse("每週大約 50 公里")
    assert result and result.monthly_mileage == 216.5


def test_rules_convert_weekly_mileage_without_calling_ai() -> None:
    def should_not_call_ai(*args: object, **kwargs: object) -> FakeResponse:
        raise AssertionError("明確的每週里程不應送給 AI")

    parser = MileageParser(api_key="test", post=should_not_call_ai)
    result = parser.parse("每週 40～60 公里")
    assert result and result.monthly_mileage == 216.5
    assert result.interpretation == "每週 50 公里"


def test_rules_convert_commute_one_way_to_monthly_round_trips() -> None:
    parser = MileageParser(api_key="", post=None)
    result = parser.parse("上下班單程 10 公里")
    assert result and result.monthly_mileage == 440


def test_rules_convert_weekly_frequency_and_distance() -> None:
    parser = MileageParser(api_key="", post=None)
    result = parser.parse("每週開 3 次，每次 12 公里")
    assert result and result.monthly_mileage == 155.88


def test_vague_weekend_driving_has_a_safe_local_clarification() -> None:
    parser = MileageParser(api_key="", post=None)
    result = parser.parse("平常只有週末回家會開一下")
    assert result and result.status == "need_clarification"


def test_rules_accept_conversational_monthly_number_without_ai() -> None:
    parser = MileageParser(api_key="", post=None)
    result = parser.parse("可能 1200 吧")
    assert result and result.monthly_mileage == 1200


def test_parser_keeps_ambiguous_driving_frequency_unquantified() -> None:
    parser = MileageParser(api_key="test", post=lambda *args, **kwargs: FakeResponse({"status": "need_clarification", "monthly_mileage": None, "interpretation": None, "reply": "你比較接近每月 0–300、300–800，還是 800 公里以上？"}))
    result = parser.parse("我偶爾才開")
    assert result and result.status == "need_clarification"
