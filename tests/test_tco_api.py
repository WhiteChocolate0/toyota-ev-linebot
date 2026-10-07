from fastapi.testclient import TestClient

from app.main import app


def test_tco_api_returns_server_calculated_total_and_assumption_version() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/cost/calculate", json={
        "vehicle_a": {
            "name": "bZ4X", "powertrain": "ev", "purchase_price": 1280000, "energy_efficiency": 6,
            "annual_maintenance": 8000, "annual_insurance": 18000, "residual_rates": {"base": 0.45},
        },
        "vehicle_b": {
            "name": "RAV4 Hybrid", "powertrain": "hybrid", "purchase_price": 1220000, "energy_efficiency": 18,
            "annual_maintenance": 12000, "annual_insurance": 18000, "annual_tax": 12000, "residual_rates": {"base": 0.5},
        },
        "annual_mileage": 15000,
        "ownership_years": 5,
        "fuel_price_per_liter": 32.7,
        "home_electricity_price": 3.5,
        "public_electricity_price": 8,
        "home_charge_ratio": 0.8,
        "public_charge_ratio": 0.2,
        "residual_scenario": "base",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_a"]["name"] == "bZ4X"
    assert body["vehicle_a"]["monthly_average"] > 0
    assert body["vehicle_a"]["components"]["energy"] == 55000
    assert body["vehicle_a"]["cost_per_km"] == 11.85
    assert body["assumption_version"] == "2026Q3_TW"


def test_tco_api_rejects_invalid_charging_mix() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/cost/calculate", json={
        "vehicle_a": {"name": "bZ4X", "powertrain": "ev", "purchase_price": 1, "energy_efficiency": 6},
        "vehicle_b": {"name": "RAV4", "powertrain": "hybrid", "purchase_price": 1, "energy_efficiency": 18},
        "annual_mileage": 15000,
        "fuel_price_per_liter": 32.7,
        "home_electricity_price": 3.5,
        "public_electricity_price": 8,
        "home_charge_ratio": 0.8,
        "public_charge_ratio": 0.1,
    })

    assert response.status_code == 422
    assert "must sum to 1" in response.json()["detail"]
