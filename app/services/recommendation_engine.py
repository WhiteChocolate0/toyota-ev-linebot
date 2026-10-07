"""Structured, explainable vehicle shortlisting from verified catalog fields."""

from dataclasses import dataclass, field
import re

from app.services.powertrain import BEV, ICE_DIESEL, ICE_GASOLINE, normalize_powertrain


@dataclass
class VehiclePreferenceProfile:
    budget_max: int | None = None
    preferred_powertrains: set[str] = field(default_factory=set)
    excluded_powertrains: set[str] = field(default_factory=set)
    cargo_space_priority: str | None = None
    passenger_space_priority: str | None = None
    seat_requirement: int | None = None
    daily_mileage_km: int | None = None
    long_trip_frequency: str | None = None
    home_charging_status: str | None = None
    usage_scenarios: set[str] = field(default_factory=set)
    priority_factors: set[str] = field(default_factory=set)
    concern_factors: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Candidate:
    vehicle: dict
    reasons: tuple[str, ...]
    cautions: tuple[str, ...]


def extract_vehicle_preferences(text: str) -> VehiclePreferenceProfile:
    """Extract only explicit, user-stated constraints; unknown remains null."""
    profile = VehiclePreferenceProfile()
    budget = re.search(r"(?:預算|抓|拉到)\s*(?:大概|約)?\s*(\d+(?:\.\d+)?)\s*(萬|元)?", text)
    if budget:
        value = float(budget.group(1)); profile.budget_max = int(value * 10000) if budget.group(2) == "萬" or value < 10000 else int(value)
    seats = re.search(r"([2-9])\s*個?人", text)
    chinese_seats = next((number for word, number in (("兩", 2), ("三", 3), ("四", 4), ("五", 5), ("六", 6), ("七", 7)) if f"{word}個人" in text), None)
    if seats or chinese_seats:
        profile.seat_requirement = int(seats.group(1)) if seats else chinese_seats
        profile.usage_scenarios.add("family"); profile.passenger_space_priority = "high"
    daily = re.search(r"每天\s*(?:大概|約)?\s*(\d+)\s*(?:公里|km)", text, re.I)
    if daily: profile.daily_mileage_km = int(daily.group(1))
    if any(word in text for word in ("後車廂", "行李廂", "嬰兒車", "露營")):
        profile.cargo_space_priority = "high"; profile.priority_factors.add("space")
    if "嬰兒車" in text: profile.usage_scenarios.add("stroller")
    if "露營" in text: profile.usage_scenarios.add("camping")
    if any(word in text for word in ("長途", "出遊", "跨縣市")): profile.long_trip_frequency = "frequent"; profile.usage_scenarios.add("road_trip")
    if any(word in text for word in ("充電樁", "可以裝充電", "220v")): profile.home_charging_status = "available_220v"; profile.priority_factors.add("charging")
    if any(word in text for word in ("怕電池", "電池壞")): profile.concern_factors.add("battery")
    if any(word in text for word in ("怕充電", "充電麻煩")): profile.concern_factors.add("charging")
    if any(word in text for word in ("省", "成本", "預算")): profile.priority_factors.add("cost")
    if "不要純油車" in text or "不要油車" in text: profile.excluded_powertrains.update({ICE_GASOLINE, ICE_DIESEL})
    for wording, powertrain in (("純電", BEV), ("電動車", BEV), ("油電", "HEV"), ("插電油電", "PHEV")):
        if wording in text and not text.startswith("不要"):
            profile.preferred_powertrains.add(powertrain)
    return profile


def merge_preferences(current: VehiclePreferenceProfile, update: VehiclePreferenceProfile) -> VehiclePreferenceProfile:
    for name in ("budget_max", "cargo_space_priority", "passenger_space_priority", "seat_requirement", "daily_mileage_km", "long_trip_frequency", "home_charging_status"):
        value = getattr(update, name)
        if value is not None: setattr(current, name, value)
    for name in ("preferred_powertrains", "excluded_powertrains", "usage_scenarios", "priority_factors", "concern_factors"):
        getattr(current, name).update(getattr(update, name))
    return current


def recommendation_readiness(profile: VehiclePreferenceProfile) -> str | None:
    if profile.budget_max is None: return "目前我知道你的使用需求了；預算大概抓在哪個範圍？"
    if not profile.usage_scenarios and not profile.cargo_space_priority and not profile.seat_requirement: return "你平常最在意空間、通勤、家庭出遊，還是長途使用？"
    if not profile.priority_factors: return "選車時你最重視成本、空間、充電便利，還是長途續航？"
    return None


def shortlist_candidates(profile: VehiclePreferenceProfile, vehicles: list[dict], limit: int = 3) -> list[Candidate]:
    shortlisted: list[tuple[int, Candidate]] = []
    for vehicle in vehicles:
        drivetrain = normalize_powertrain(str(vehicle.get("drivetrain", ""))) or str(vehicle.get("drivetrain", ""))
        price, seats = vehicle.get("purchase_price_ntd"), vehicle.get("seats")
        if profile.budget_max and isinstance(price, (int, float)) and price > profile.budget_max: continue
        if profile.seat_requirement and isinstance(seats, int) and seats < profile.seat_requirement: continue
        if drivetrain in profile.excluded_powertrains: continue
        score, reasons, cautions = 0, [], []
        if profile.budget_max and isinstance(price, (int, float)):
            score += 3; reasons.append("官方建議售價在你的預算範圍內")
        if profile.seat_requirement:
            if isinstance(seats, int): score += 3; reasons.append(f"官方資料列有 {seats} 人座，可對應家庭乘坐需求")
            else: cautions.append("官方座位資料尚待確認")
        if profile.cargo_space_priority:
            if vehicle.get("cargo_capacity_l"):
                score += 3; reasons.append("官方已公布可比較的行李廂容量")
            elif vehicle.get("body_type") or vehicle.get("rear_seat_foldable"):
                score += 1; reasons.append("官方資料可比較車型／後座傾倒資訊")
                cautions.append("官方目前未公布可比較的行李廂公升數")
            else: cautions.append("官方目前未公布可比較的行李廂公升數")
        if profile.preferred_powertrains and drivetrain in profile.preferred_powertrains:
            score += 2; reasons.append("符合你偏好的動力型態")
        if drivetrain == BEV and profile.home_charging_status == "available_220v":
            score += 2; reasons.append("家用充電條件可支援純電日常補電")
        elif drivetrain == BEV and profile.home_charging_status != "available_220v":
            cautions.append("長途與日常補電仍需確認充電安排")
        if profile.long_trip_frequency == "frequent" and drivetrain == BEV:
            cautions.append("長途使用需要先規劃充電")
        if not reasons: continue
        shortlisted.append((score, Candidate(vehicle, tuple(reasons[:3]), tuple(dict.fromkeys(cautions)))))
    return [candidate for _score, candidate in sorted(shortlisted, key=lambda item: (-item[0], str(item[1].vehicle.get("model_name", ""))))[:limit]]


class RecommendationEngine:
    """Keeps an in-process profile while the repository persists a safe JSON copy."""
    def __init__(self) -> None:
        self._profiles: dict[str, VehiclePreferenceProfile] = {}

    def update(self, scope_id: str, text: str) -> VehiclePreferenceProfile:
        profile = self._profiles.setdefault(scope_id, VehiclePreferenceProfile())
        return merge_preferences(profile, extract_vehicle_preferences(text))

    def profile(self, scope_id: str) -> VehiclePreferenceProfile | None:
        return self._profiles.get(scope_id)

    def clear(self, scope_id: str) -> None:
        """Cancelled/expired recommendation sessions must not leak slots."""
        self._profiles.pop(scope_id, None)

    def apply_ev_fit(self, scope_id: str, values: dict[str, str]) -> VehiclePreferenceProfile:
        """Reuse completed EV-fit inputs instead of asking a second time."""
        profile = self._profiles.setdefault(scope_id, VehiclePreferenceProfile())
        daily = {"under_20": 20, "20_40": 40, "40_60": 60, "60_100": 80, "over_100": 100}
        if values.get("daily_km") in daily: profile.daily_mileage_km = daily[values["daily_km"]]
        if values.get("long_trip") in {"monthly", "weekly"}: profile.long_trip_frequency = values["long_trip"]
        if values.get("home_charge") == "HOME_220V": profile.home_charging_status = "available_220v"
        elif values.get("home_charge"): profile.home_charging_status = values["home_charge"].lower()
        return profile

    @staticmethod
    def serialise(profile: VehiclePreferenceProfile) -> dict:
        return {name: sorted(value) if isinstance(value, set) else value for name, value in vars(profile).items()}


recommendation_engine = RecommendationEngine()
