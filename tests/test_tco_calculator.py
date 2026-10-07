import pytest

from app.services.tco_calculator import LoanTerms, TcoCalculator, TcoInputs, VehicleTcoProfile


BZ4X = VehicleTcoProfile(
    name="bZ4X",
    powertrain="ev",
    purchase_price=1_280_000,
    energy_efficiency=6,
    annual_maintenance=8_000,
    annual_insurance=18_000,
    annual_tax=0,
    tire_set_price=20_000,
    tire_lifespan_km=40_000,
    residual_rates={"conservative": 0.35, "base": 0.45, "optimistic": 0.55},
)
RAV4 = VehicleTcoProfile(
    name="RAV4 Hybrid",
    powertrain="hybrid",
    purchase_price=1_220_000,
    energy_efficiency=18,
    annual_maintenance=12_000,
    annual_insurance=18_000,
    annual_tax=12_000,
    tire_set_price=20_000,
    tire_lifespan_km=40_000,
    residual_rates={"conservative": 0.4, "base": 0.5, "optimistic": 0.6},
)


def test_tco_includes_all_configured_cost_categories_and_residual_credit() -> None:
    result = TcoCalculator().compare(
        BZ4X,
        RAV4,
        TcoInputs(
            annual_mileage=15_000,
            ownership_years=5,
            fuel_price_per_liter=32.7,
            home_electricity_price=3.5,
            public_electricity_price=8,
            home_charge_ratio=0.8,
            public_charge_ratio=0.2,
            annual_parking=12_000,
            annual_miscellaneous=2_000,
            charger_installation_cost=30_000,
            residual_scenario="base",
        ),
    )

    assert result.vehicle_a.components["charger_installation"] == 30_000
    assert result.vehicle_b.components["charger_installation"] == 0
    assert result.vehicle_a.components["residual_value_credit"] == -576_000
    assert result.vehicle_b.components["tires"] == 20_000
    assert result.assumption_version == "2026Q3_TW"


def test_tco_can_exclude_residual_value_when_no_reliable_scenario_exists() -> None:
    result = TcoCalculator().calculate(
        BZ4X,
        TcoInputs(
            annual_mileage=15_000,
            fuel_price_per_liter=32.7,
            home_electricity_price=3.5,
            public_electricity_price=8,
            residual_scenario="exclude",
        ),
    )

    assert result.residual_rate is None
    assert result.components["residual_value_credit"] == 0


def test_tco_validates_charging_mix_and_mileage_boundaries() -> None:
    with pytest.raises(ValueError, match="Charging ratios"):
        TcoCalculator().calculate(
            BZ4X,
            TcoInputs(annual_mileage=15_000, home_charge_ratio=1.2, public_charge_ratio=-0.2),
        )

    with pytest.raises(ValueError, match="Annual mileage"):
        TcoCalculator().calculate(
            RAV4,
            TcoInputs(annual_mileage=100_001, fuel_price_per_liter=32.7),
        )


def test_tco_includes_loan_interest_without_treating_principal_as_an_extra_cost() -> None:
    result = TcoCalculator().calculate(
        RAV4,
        TcoInputs(
            annual_mileage=15_000,
            fuel_price_per_liter=32.7,
            loan=LoanTerms(enabled=True, down_payment=400_000, annual_interest_rate=0.025, years=5, fee=3_000),
        ),
    )

    assert result.components["loan_interest"] > 0
    assert result.components["loan_fee"] == 3_000


def test_phev_energy_cost_combines_fuel_and_electricity_by_electric_mileage_share() -> None:
    phev = VehicleTcoProfile(
        name="RAV4 PHEV", powertrain="PHEV", purchase_price=1_500_000,
        fuel_efficiency=16, electric_efficiency=5, annual_maintenance=10_000,
    )
    result = TcoCalculator().calculate(
        phev,
        TcoInputs(
            annual_mileage=12_000, ownership_years=1, fuel_price_per_liter=32,
            home_electricity_price=4, public_electricity_price=8,
            home_charge_ratio=0.5, public_charge_ratio=0.5,
            phev_electric_mileage_ratio=0.6,
        ),
    )
    # 4,800 km gasoline / 16 km/L × $32 + 7,200 km electricity / 5 km/kWh × $6.
    assert result.components["energy"] == 18_240
