import json
import logging
from dataclasses import asdict

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.event_processor import event_processor
from app.services.line_signature import verify_line_signature
from app.services.tco_calculator import LoanTerms, TcoCalculator, TcoInputs, VehicleTcoProfile

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="TOYOTA EV 家庭小幫手 LINE Bot", version="0.1.0")


class TcoVehicleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    powertrain: str
    purchase_price: float = Field(ge=0)
    energy_efficiency: float | None = Field(default=None, gt=0)
    fuel_efficiency: float | None = Field(default=None, gt=0)
    electric_efficiency: float | None = Field(default=None, gt=0)
    annual_maintenance: float = Field(default=0, ge=0)
    annual_insurance: float = Field(default=0, ge=0)
    annual_tax: float = Field(default=0, ge=0)
    tire_set_price: float = Field(default=0, ge=0)
    tire_lifespan_km: float = Field(default=0, ge=0)
    residual_rates: dict[str, float] = Field(default_factory=dict)


class TcoLoanRequest(BaseModel):
    enabled: bool = False
    down_payment: float = Field(default=0, ge=0)
    annual_interest_rate: float = Field(default=0, ge=0, le=1)
    years: int = Field(default=0, ge=0, le=15)
    fee: float = Field(default=0, ge=0)


class TcoCalculationRequest(BaseModel):
    vehicle_a: TcoVehicleRequest
    vehicle_b: TcoVehicleRequest
    annual_mileage: float = Field(gt=0, le=100_000)
    ownership_years: int = Field(default=8, ge=1, le=15)
    fuel_price_per_liter: float | None = Field(default=None, gt=0)
    home_electricity_price: float | None = Field(default=None, gt=0)
    public_electricity_price: float | None = Field(default=None, gt=0)
    home_charge_ratio: float = Field(default=1, ge=0, le=1)
    public_charge_ratio: float = Field(default=0, ge=0, le=1)
    phev_electric_mileage_ratio: float = Field(default=0, ge=0, le=1)
    annual_parking: float = Field(default=0, ge=0)
    annual_miscellaneous: float = Field(default=0, ge=0)
    charger_installation_cost: float = Field(default=0, ge=0)
    loan: TcoLoanRequest = Field(default_factory=TcoLoanRequest)
    residual_scenario: str = Field(default="exclude", pattern="^(exclude|conservative|base|optimistic)$")
    assumption_version: str = Field(default="2026Q3_TW", min_length=1, max_length=40)


def _to_vehicle_profile(vehicle: TcoVehicleRequest) -> VehicleTcoProfile:
    return VehicleTcoProfile(**vehicle.model_dump())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/cost/calculate")
async def calculate_tco(request: TcoCalculationRequest) -> dict:
    """Calculate TCO server-side so every client uses identical assumptions."""
    try:
        inputs = TcoInputs(
            annual_mileage=request.annual_mileage,
            ownership_years=request.ownership_years,
            fuel_price_per_liter=request.fuel_price_per_liter,
            home_electricity_price=request.home_electricity_price,
            public_electricity_price=request.public_electricity_price,
            home_charge_ratio=request.home_charge_ratio,
            public_charge_ratio=request.public_charge_ratio,
            phev_electric_mileage_ratio=request.phev_electric_mileage_ratio,
            annual_parking=request.annual_parking,
            annual_miscellaneous=request.annual_miscellaneous,
            charger_installation_cost=request.charger_installation_cost,
            loan=LoanTerms(**request.loan.model_dump()),
            residual_scenario=request.residual_scenario,
            assumption_version=request.assumption_version,
        )
        result = TcoCalculator().compare(_to_vehicle_profile(request.vehicle_a), _to_vehicle_profile(request.vehicle_b), inputs)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return asdict(result)


@app.post("/webhook", status_code=status.HTTP_200_OK)
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str | None = Header(default=None),
) -> dict[str, str]:
    """Accept LINE events and acknowledge immediately after signature verification."""
    settings = get_settings()
    raw_body = await request.body()

    if not verify_line_signature(
        body=raw_body,
        signature=x_line_signature,
        channel_secret=settings.line_channel_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc

    events = payload.get("events", [])
    if not isinstance(events, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid events payload")

    background_tasks.add_task(event_processor.process, events)
    return {"status": "accepted"}
