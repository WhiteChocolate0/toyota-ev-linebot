import pytest

from app.services.vehicle_matcher import (
    is_explicit_vehicle_comparison,
    find_vehicles_in_text,
    match_vehicle_in_text,
    match_vehicle_name,
)


PROFILES = [
    {"model_name": "RAV4", "aliases": ["rav4", "RAV 4"]},
    {"model_name": "COROLLA CROSS", "aliases": ["corolla cross", "CorollaCross", "CC"]},
]


@pytest.mark.parametrize("text,expected", [("rav 4", "RAV4"), ("CorollaCross", "COROLLA CROSS"), ("cc", "COROLLA CROSS")])
def test_aliases_match_regardless_of_spacing_or_case(text: str, expected: str) -> None:
    assert match_vehicle_name(text, PROFILES)["model_name"] == expected


def test_unknown_vehicle_returns_none() -> None:
    assert match_vehicle_name("Unknown Model", PROFILES) is None


def test_model_can_be_found_inside_a_personal_message() -> None:
    assert match_vehicle_in_text("我現在開 rav 4，想比較成本", PROFILES)["model_name"] == "RAV4"


def test_all_distinct_vehicles_are_retained_as_structured_context() -> None:
    profiles = [*PROFILES, {"model_name": "bZ4X", "aliases": ["bz4x"]}]
    assert [profile["model_name"] for profile in find_vehicles_in_text("RAV4 跟 bZ4X 比較", profiles)] == ["RAV4", "bZ4X"]


def test_short_alias_must_be_a_standalone_token() -> None:
    assert match_vehicle_in_text("account", PROFILES) is None
    assert match_vehicle_in_text("我的是 CC", PROFILES)["model_name"] == "COROLLA CROSS"


def test_comparison_detection_requires_a_comparison_marker() -> None:
    assert is_explicit_vehicle_comparison("RAV4 跟 bZ4X 怎麼比較？")
    assert not is_explicit_vehicle_comparison("我家的是 RAV4")
    assert not is_explicit_vehicle_comparison("我跟家人都開 RAV4")
