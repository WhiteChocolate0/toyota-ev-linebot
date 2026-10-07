from app.services.cost_sensitivity import apply_scenario


def test_scenario_does_not_mutate_base_and_changes_only_mileage() -> None:
    base = {"monthly_km": 1000, "ownership_years": 5, "home_charge_ratio": .8, "public_charge_ratio": .2}
    scenario, override = apply_scenario(base, "HIGH_MILEAGE")
    assert base["monthly_km"] == 1000 and scenario["monthly_km"] == 1800
    assert scenario["ownership_years"] == 5 and override == {"monthly_km": 1800}


def test_public_charging_scenario_changes_only_charge_split() -> None:
    base = {"monthly_km": 1000, "home_charge_ratio": .8, "public_charge_ratio": .2}
    scenario, _ = apply_scenario(base, "PUBLIC_CHARGING_HEAVY")
    assert scenario["monthly_km"] == 1000 and (scenario["home_charge_ratio"], scenario["public_charge_ratio"]) == (.2, .8)
