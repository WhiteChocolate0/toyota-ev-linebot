from app.services.recommendation_engine import (
    VehiclePreferenceProfile, extract_vehicle_preferences, merge_preferences,
    recommendation_readiness, shortlist_candidates,
)
from app.services.powertrain import BEV, HEV, ICE_GASOLINE


VEHICLES = [
    {"id": "bz", "model_name": "bZ4X", "drivetrain": BEV, "purchase_price_ntd": 1290000, "seats": 5, "body_type": "SUV", "rear_seat_foldable": True},
    {"id": "rav", "model_name": "RAV4 Hybrid", "drivetrain": HEV, "purchase_price_ntd": 1260000, "seats": 5, "body_type": "SUV", "rear_seat_foldable": True},
    {"id": "ice", "model_name": "COROLLA CROSS", "drivetrain": ICE_GASOLINE, "purchase_price_ntd": 900000, "seats": 5, "body_type": "SUV"},
]


def test_family_language_builds_ready_profile_and_shortlist_without_invented_cargo() -> None:
    profile = extract_vehicle_preferences("家裡五個人，常出遊，想要後車廂大一點，預算 130 萬")
    assert profile.seat_requirement == 5 and profile.budget_max == 1_300_000
    assert profile.cargo_space_priority == "high" and "road_trip" in profile.usage_scenarios
    assert recommendation_readiness(profile) is None
    candidates = shortlist_candidates(profile, VEHICLES)
    assert 2 <= len(candidates) <= 3
    assert all("公升數" not in reason for candidate in candidates for reason in candidate.reasons)
    assert any("公升數" in caution for candidate in candidates for caution in candidate.cautions)


def test_excluding_ice_and_updating_budget_reranks_same_profile() -> None:
    profile = extract_vehicle_preferences("家裡五個人，後車廂想大一點，預算 130 萬")
    merge_preferences(profile, extract_vehicle_preferences("不要純油車"))
    assert ICE_GASOLINE in profile.excluded_powertrains
    assert all(candidate.vehicle["drivetrain"] != ICE_GASOLINE for candidate in shortlist_candidates(profile, VEHICLES))
    merge_preferences(profile, extract_vehicle_preferences("預算拉到 150 萬"))
    assert profile.budget_max == 1_500_000


def test_readiness_asks_one_high_value_question_at_a_time() -> None:
    profile = VehiclePreferenceProfile(cargo_space_priority="high", priority_factors={"space"})
    assert "預算" in recommendation_readiness(profile)
