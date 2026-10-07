"""Transparent five-year (or user-selected) total-cost-of-ownership calculator."""

from dataclasses import dataclass, field
from math import floor

from app.services.powertrain import BEV, PHEV, normalize_powertrain


@dataclass(frozen=True)
class VehicleTcoProfile:
    name: str
    powertrain: str  # ICE_GASOLINE, ICE_DIESEL, HEV, PHEV, BEV
    purchase_price: float
    energy_efficiency: float | None = None  # legacy: km/L for fuel vehicles; km/kWh for BEV
    fuel_efficiency: float | None = None  # PHEV / fuel vehicles: km/L
    electric_efficiency: float | None = None  # PHEV / BEV: km/kWh
    annual_maintenance: float = 0
    annual_insurance: float = 0
    annual_tax: float = 0
    tire_set_price: float = 0
    tire_lifespan_km: float = 0
    residual_rates: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LoanTerms:
    enabled: bool = False
    down_payment: float = 0
    annual_interest_rate: float = 0
    years: int = 0
    fee: float = 0


@dataclass(frozen=True)
class TcoInputs:
    annual_mileage: float
    ownership_years: int = 5
    fuel_price_per_liter: float | None = None
    home_electricity_price: float | None = None
    public_electricity_price: float | None = None
    home_charge_ratio: float = 1
    public_charge_ratio: float = 0
    phev_electric_mileage_ratio: float = 0
    annual_parking: float = 0
    annual_miscellaneous: float = 0
    charger_installation_cost: float = 0
    loan: LoanTerms = field(default_factory=LoanTerms)
    residual_scenario: str = "exclude"
    assumption_version: str = "2026Q3_TW"


@dataclass(frozen=True)
class VehicleTcoResult:
    name: str
    components: dict[str, float]
    total_cost: float
    monthly_average: float
    cost_per_km: float
    residual_scenario: str
    residual_rate: float | None


@dataclass(frozen=True)
class TcoComparisonResult:
    vehicle_a: VehicleTcoResult
    vehicle_b: VehicleTcoResult
    difference_by_category: dict[str, float]
    total_difference: float
    assumption_version: str


class TcoCalculator:
    """Performs arithmetic only; source validation belongs to the data layer."""

    def compare(
        self,
        vehicle_a: VehicleTcoProfile,
        vehicle_b: VehicleTcoProfile,
        inputs: TcoInputs,
    ) -> TcoComparisonResult:
        self._validate_inputs(inputs)
        result_a = self.calculate(vehicle_a, inputs)
        result_b = self.calculate(vehicle_b, inputs)
        categories = set(result_a.components) | set(result_b.components)
        differences = {
            category: result_b.components.get(category, 0) - result_a.components.get(category, 0)
            for category in sorted(categories)
        }
        return TcoComparisonResult(
            vehicle_a=result_a,
            vehicle_b=result_b,
            difference_by_category=differences,
            total_difference=result_b.total_cost - result_a.total_cost,
            assumption_version=inputs.assumption_version,
        )

    def calculate(self, vehicle: VehicleTcoProfile, inputs: TcoInputs) -> VehicleTcoResult:
        vehicle = self._normalized_vehicle(vehicle)
        self._validate_inputs(inputs)
        total_distance = inputs.annual_mileage * inputs.ownership_years
        residual_rate = self._residual_rate(vehicle, inputs.residual_scenario)
        components = {
            "purchase_price": vehicle.purchase_price,
            "energy": self._energy_cost(vehicle, inputs, total_distance),
            "maintenance": vehicle.annual_maintenance * inputs.ownership_years,
            "insurance": vehicle.annual_insurance * inputs.ownership_years,
            "tax": vehicle.annual_tax * inputs.ownership_years,
            "tires": self._tire_cost(vehicle, total_distance),
            "parking": inputs.annual_parking * inputs.ownership_years,
            "miscellaneous": inputs.annual_miscellaneous * inputs.ownership_years,
            "loan_interest": self._loan_interest(vehicle.purchase_price, inputs.loan),
            "loan_fee": inputs.loan.fee if inputs.loan.enabled else 0,
            "charger_installation": inputs.charger_installation_cost if vehicle.powertrain in {BEV, PHEV} else 0,
            "residual_value_credit": -(vehicle.purchase_price * residual_rate) if residual_rate is not None else 0,
        }
        # NTD component amounts are presented as whole dollars; unit metrics
        # retain two decimals without exposing binary floating-point artefacts.
        components = {category: round(amount) for category, amount in components.items()}
        total_cost = round(sum(components.values()))
        return VehicleTcoResult(
            name=vehicle.name,
            components=components,
            total_cost=total_cost,
            monthly_average=round(total_cost / (inputs.ownership_years * 12), 2),
            cost_per_km=round(total_cost / total_distance, 2),
            residual_scenario=inputs.residual_scenario,
            residual_rate=residual_rate,
        )

    @staticmethod
    def _energy_cost(vehicle: VehicleTcoProfile, inputs: TcoInputs, total_distance: float) -> float:
        if vehicle.powertrain == BEV:
            if inputs.home_electricity_price is None or inputs.public_electricity_price is None:
                raise ValueError("BEV calculation requires home and public electricity prices")
            return total_distance / vehicle.electric_efficiency * TcoCalculator._average_electricity_price(inputs)
        if vehicle.powertrain == PHEV:
            if inputs.fuel_price_per_liter is None:
                raise ValueError("PHEV calculation requires a verified fuel price")
            if inputs.home_electricity_price is None or inputs.public_electricity_price is None:
                raise ValueError("PHEV calculation requires home and public electricity prices")
            electric_distance = total_distance * inputs.phev_electric_mileage_ratio
            fuel_distance = total_distance - electric_distance
            return (
                fuel_distance / vehicle.fuel_efficiency * inputs.fuel_price_per_liter
                + electric_distance / vehicle.electric_efficiency * TcoCalculator._average_electricity_price(inputs)
            )
        if inputs.fuel_price_per_liter is None:
            raise ValueError("Fuel-vehicle calculation requires a verified fuel price")
        return total_distance / vehicle.fuel_efficiency * inputs.fuel_price_per_liter

    @staticmethod
    def _average_electricity_price(inputs: TcoInputs) -> float:
        return inputs.home_charge_ratio * inputs.home_electricity_price + inputs.public_charge_ratio * inputs.public_electricity_price

    @staticmethod
    def _tire_cost(vehicle: VehicleTcoProfile, total_distance: float) -> float:
        if not vehicle.tire_set_price or not vehicle.tire_lifespan_km:
            return 0
        return floor(total_distance / vehicle.tire_lifespan_km) * vehicle.tire_set_price

    @staticmethod
    def _loan_interest(purchase_price: float, loan: LoanTerms) -> float:
        if not loan.enabled:
            return 0
        principal = max(purchase_price - loan.down_payment, 0)
        if not principal or not loan.years or not loan.annual_interest_rate:
            return 0
        monthly_rate = loan.annual_interest_rate / 12
        months = loan.years * 12
        monthly_payment = principal * monthly_rate * (1 + monthly_rate) ** months / ((1 + monthly_rate) ** months - 1)
        return monthly_payment * months - principal

    @staticmethod
    def _residual_rate(vehicle: VehicleTcoProfile, scenario: str) -> float | None:
        if scenario == "exclude":
            return None
        rate = vehicle.residual_rates.get(scenario)
        if rate is None:
            return None
        return rate

    @staticmethod
    def _normalized_vehicle(vehicle: VehicleTcoProfile) -> VehicleTcoProfile:
        powertrain = normalize_powertrain(vehicle.powertrain)
        if powertrain is None:
            raise ValueError("Unsupported powertrain")
        fuel_efficiency = vehicle.fuel_efficiency or (vehicle.energy_efficiency if powertrain not in {BEV, PHEV} else None)
        electric_efficiency = vehicle.electric_efficiency or (vehicle.energy_efficiency if powertrain == BEV else None)
        if vehicle.purchase_price < 0:
            raise ValueError("Vehicle price and efficiency must be valid")
        if powertrain in {BEV, PHEV} and (electric_efficiency is None or electric_efficiency <= 0):
            raise ValueError(f"{powertrain} requires electric_efficiency")
        if powertrain != BEV and (fuel_efficiency is None or fuel_efficiency <= 0):
            raise ValueError(f"{powertrain} requires fuel_efficiency")
        if any(not 0 <= rate <= 1 for rate in vehicle.residual_rates.values()):
            raise ValueError("Residual rates must be between 0 and 1")
        return VehicleTcoProfile(
            **{**vehicle.__dict__, "powertrain": powertrain, "fuel_efficiency": fuel_efficiency,
               "electric_efficiency": electric_efficiency}
        )

    @staticmethod
    def _validate_inputs(inputs: TcoInputs) -> None:
        if not 0 < inputs.annual_mileage <= 100_000:
            raise ValueError("Annual mileage must be between 1 and 100000")
        if not 1 <= inputs.ownership_years <= 15:
            raise ValueError("Ownership years must be between 1 and 15")
        if not 0 <= inputs.home_charge_ratio <= 1 or not 0 <= inputs.public_charge_ratio <= 1:
            raise ValueError("Charging ratios must be between 0 and 1")
        if abs(inputs.home_charge_ratio + inputs.public_charge_ratio - 1) > 1e-9:
            raise ValueError("Home and public charging ratios must sum to 1")
        if not 0 <= inputs.phev_electric_mileage_ratio <= 1:
            raise ValueError("PHEV electric mileage ratio must be between 0 and 1")
        if inputs.loan.annual_interest_rate < 0 or inputs.loan.down_payment < 0 or inputs.loan.fee < 0:
            raise ValueError("Loan values must not be negative")
