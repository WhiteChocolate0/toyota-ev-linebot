"""Immutable scenario overrides for deterministic two-car cost calculations."""
from copy import deepcopy
import re

SCENARIOS = {
    "LOW_MILEAGE": {"monthly_km": 600}, "HIGH_MILEAGE": {"monthly_km": 1800},
    "SHORT_OWNERSHIP": {"ownership_years": 3}, "LONG_OWNERSHIP": {"ownership_years": 8},
    "HOME_CHARGING_HEAVY": {"home_charge_ratio": .8, "public_charge_ratio": .2},
    "PUBLIC_CHARGING_HEAVY": {"home_charge_ratio": .2, "public_charge_ratio": .8},
    "FUEL_PRICE_UP": {"fuel_price_multiplier": 1.1}, "ELECTRICITY_PRICE_UP": {"electricity_price_multiplier": 1.1},
}

def apply_scenario(base: dict[str, object], scenario_type: str) -> tuple[dict[str, object], dict[str, object]]:
    override = dict(SCENARIOS[scenario_type]); result = deepcopy(base)
    if "fuel_price_multiplier" in override: result["fuel_price"] = float(result.get("fuel_price", 0)) * float(override.pop("fuel_price_multiplier"))
    if "electricity_price_multiplier" in override:
        factor = float(override.pop("electricity_price_multiplier")); result["home_electricity_price"] = float(result.get("home_electricity_price", 0)) * factor; result["public_charging_price"] = float(result.get("public_charging_price", 0)) * factor
    result.update(override)
    return result, SCENARIOS[scenario_type]

def difference(text: str) -> str:
    match = re.search(r"每年約差：NT\$ ([\d,]+)", text)
    return match.group(1) if match else "—"
