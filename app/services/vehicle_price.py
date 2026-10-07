"""Deterministic vehicle-price routing, deliberately separate from TCO."""

from dataclasses import dataclass


PRICE_MARKERS = ("車價", "售價", "定價", "價格", "賣多少", "多少錢", "要多少錢")
PRICE_FOLLOWUPS = ("多少錢", "多少", "車價多少", "車價呢", "售價呢", "價格呢", "定價多少", "這台多少", "這台多少錢", "賣多少", "要多少錢")
OWNERSHIP_MARKERS = ("每月", "每年", "油費", "電費", "保養", "保險", "持有", "成本", "省", "tco", "養車")


def is_ownership_cost_question(text: str) -> bool:
    compact = text.replace(" ", "").lower()
    return any(marker in compact for marker in OWNERSHIP_MARKERS)


def is_vehicle_price_question(text: str) -> bool:
    """Only route price wording here when it is not a use-cost question."""
    compact = text.replace(" ", "").lower().rstrip("？?")
    if is_ownership_cost_question(compact):
        return False
    return compact in PRICE_FOLLOWUPS or any(marker in compact for marker in PRICE_MARKERS)


@dataclass(frozen=True)
class PriceResolution:
    kind: str  # PRICE, NEED_VEHICLE, DISAMBIGUATE
    profiles: tuple[dict, ...] = ()


def resolve_vehicle_price(text: str, active_vehicle_id: str | None, profiles: list[dict]) -> PriceResolution | None:
    if not is_vehicle_price_question(text):
        return None
    if not active_vehicle_id:
        return PriceResolution("NEED_VEHICLE")
    current = next((row for row in profiles if str(row.get("id")) == str(active_vehicle_id)), None)
    if not current:
        return PriceResolution("NEED_VEHICLE")
    # Several powertrains under one family name (e.g. Corolla Cross gasoline /
    # HEV) cannot safely be represented by a randomly selected catalogue row.
    same_model = [row for row in profiles if str(row.get("model_name", "")).casefold() == str(current.get("model_name", "")).casefold()]
    variants = {str(row.get("drivetrain", "")).casefold() for row in same_model}
    if len(variants) > 1:
        return PriceResolution("DISAMBIGUATE", tuple(same_model))
    return PriceResolution("PRICE", (current,))


def price_answer(profile: dict) -> str:
    model = str(profile.get("model_name", "這台車"))
    trim = str(profile.get("trim_name") or "")
    price = profile.get("purchase_price_ntd")
    if not isinstance(price, (int, float)):
        return f"{model}{'｜' + trim if trim else ''}目前沒有可確認的官方建議售價。"
    label = f"{model}｜{trim}" if trim else model
    return f"{label} 目前建議售價約 NT$ {float(price):,.0f}。"


def disambiguation_answer(profiles: tuple[dict, ...]) -> str:
    model = str(profiles[0].get("model_name", "這個車系")) if profiles else "這個車系"
    choices = "、".join(sorted({str(row.get("drivetrain", "")) for row in profiles if row.get("drivetrain")}))
    return f"{model} 有不同動力或車型（{choices}），你想看哪一種的價格？"
