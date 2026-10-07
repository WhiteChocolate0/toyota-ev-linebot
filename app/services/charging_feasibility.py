"""Deterministic primary/backup charging assessment; no location claims."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ChargingFitResult:
    primary_source: str | None; backup_source: str | None; home_fit: str; work_fit: str; long_trip_fit: str; overall_fit: str; blocker: str | None

def evaluate(values: dict[str, str], daily_km: int | None, low_110v: int, warning_110v: int) -> ChargingFitResult:
    home = values.get("home_charge", "UNAVAILABLE"); work = values.get("work_charge", "unknown")
    home_fit = "good" if home == "HOME_220V" else "good" if home == "HOME_110V" and daily_km is not None and daily_km <= low_110v else "warning" if home == "HOME_110V" and daily_km is not None and daily_km <= warning_110v else "attention" if home == "HOME_110V" else "unknown"
    work_fit = "good" if work == "yes" else "warning" if work == "uncertain" else "unknown"
    primary = "HOME_220V" if home == "HOME_220V" else "HOME_110V" if home == "HOME_110V" else "WORKPLACE" if work == "yes" else None
    backup = "PUBLIC_DC" if primary else "PUBLIC_AC"
    trips, accept = values.get("long_trip"), values.get("long_charge_acceptance")
    long_fit = "attention" if trips == "weekly" and accept == "unacceptable" else "good" if trips in {"rare", "monthly"} and accept == "accept" else "warning"
    overall = "workable" if primary and home_fit != "attention" and long_fit != "attention" else "attention" if not primary or long_fit == "attention" else "warning"
    blocker = "HOME_220V_UNCONFIRMED" if home == "HOME_110V" and home_fit != "good" else "NO_RELIABLE_CHARGING" if not primary else None
    return ChargingFitResult(primary, backup, home_fit, work_fit, long_fit, overall, blocker)
