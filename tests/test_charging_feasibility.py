from app.services.charging_feasibility import evaluate

def test_home_220_is_primary() -> None:
    result = evaluate({"home_charge": "HOME_220V", "work_charge": "no", "long_trip": "monthly", "long_charge_acceptance": "accept"}, 40, 40, 80)
    assert result.primary_source == "HOME_220V" and result.overall_fit == "workable"

def test_reliable_workplace_is_workable_without_home() -> None:
    result = evaluate({"home_charge": "UNAVAILABLE", "work_charge": "yes", "long_trip": "rare", "long_charge_acceptance": "accept"}, 40, 40, 80)
    assert result.primary_source == "WORKPLACE" and result.overall_fit == "workable"

def test_110v_high_mileage_and_unacceptable_weekly_trips_need_attention() -> None:
    result = evaluate({"home_charge": "HOME_110V", "work_charge": "no", "long_trip": "weekly", "long_charge_acceptance": "unacceptable"}, 100, 40, 80)
    assert result.home_fit == "attention" and result.long_trip_fit == "attention"
