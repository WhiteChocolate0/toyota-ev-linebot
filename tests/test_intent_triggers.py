import pytest

from app.services.intent_triggers import has_explicit_cost_period, is_cost_calculator_trigger


@pytest.mark.parametrize(
    "text",
    ["成本試算", "成本計算", "5 年成本試算", "五年成本試算", "5年能源成本試算", "幫我做五年能源成本計算", "幫我算成本"],
)
def test_cost_calculator_trigger_accepts_normal_variations(text: str) -> None:
    assert is_cost_calculator_trigger(text)


def test_cost_calculator_trigger_rejects_non_calculator_message() -> None:
    assert not is_cost_calculator_trigger("我最近在看電動車")


def test_detects_whether_user_wrote_a_cost_calculation_period() -> None:
    assert has_explicit_cost_period("5 年成本試算")
    assert has_explicit_cost_period("三年成本計算")
    assert not has_explicit_cost_period("成本試算")
