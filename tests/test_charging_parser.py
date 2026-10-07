from app.services.charging_parser import ChargingParser


def test_rules_parse_home_primary_with_occasional_public_charging() -> None:
    result = ChargingParser(api_key="").parse("大多都是家裡，少部分出遠門才需要公共充電")
    assert result is not None
    assert result.home_charge_ratio == 0.8
    assert result.public_charge_ratio == 0.2
    assert result.primary_charging_type == "home"


def test_rules_parse_explicit_percentage_pair() -> None:
    result = ChargingParser(api_key="").parse("80% 家裡、20% 公共")
    assert result is not None
    assert (result.home_charge_ratio, result.public_charge_ratio) == (0.8, 0.2)


def test_rules_parse_chinese_tenths_and_mixed_charging() -> None:
    result = ChargingParser(api_key="").parse("八成家充、兩成公共")
    assert result is not None
    assert result.primary_charging_type == "home"
    mixed = ChargingParser(api_key="").parse("家裡跟公共差不多")
    assert mixed is not None and mixed.primary_charging_type == "mixed"


def test_unclear_charging_description_requires_a_choice() -> None:
    assert ChargingParser(api_key="").parse("看情況") is None
