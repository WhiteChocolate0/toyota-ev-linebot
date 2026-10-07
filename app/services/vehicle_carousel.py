"""Reusable LINE Flex carousel for server-authoritative vehicle selection."""

from app.services.powertrain import BEV, HEV, ICE_DIESEL, ICE_GASOLINE, PHEV, POWERTRAIN_LABELS, normalize_powertrain

_ICONS = {ICE_GASOLINE: "⛽", ICE_DIESEL: "🛻", HEV: "🌱", PHEV: "🔌", BEV: "⚡"}


def build_vehicle_carousel(vehicles: list[dict], slot: str, page: int = 1, per_page: int = 5) -> dict:
    """Build model-level cards, merging equivalent official trim profiles."""
    vehicles = collapse_equivalent_profiles(vehicles)
    start = (page - 1) * per_page
    selected = vehicles[start:start + per_page]
    bubbles = [_vehicle_bubble(vehicle, slot) for vehicle in selected]
    if start + per_page < len(vehicles):
        bubbles.append({"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": "還有更多車款", "weight": "bold", "size": "lg"},
            {"type": "text", "text": "查看下一頁選項", "size": "sm", "color": "#666666"},
        ]}, "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "button", "style": "secondary", "action": {
            "type": "postback", "label": "查看更多", "data": f"action=vehicle_page&slot={slot}&page={page + 1}"}}]}})
    # LINE accepts at most 12 bubbles.  This guard makes pagination safe even
    # if the caller later changes the page size.
    return {"type": "flex", "altText": "請選擇要比較的 TOYOTA 車款", "contents": {"type": "carousel", "contents": bubbles[:12]}}


def collapse_equivalent_profiles(vehicles: list[dict]) -> list[dict]:
    """Keep one representative for identical model/powertrain/efficiency rows.

    `vehicle_profiles` is trim-granular for auditability, whereas the selector
    is deliberately model-granular.  Different models are never merged merely
    because their km/L happen to match.
    """
    grouped: dict[tuple[str, str, float | None, float | None], list[dict]] = {}
    for vehicle in vehicles:
        powertrain = normalize_powertrain(str(vehicle.get("drivetrain", vehicle.get("powertrain", "")))) or ""
        key = (
            str(vehicle.get("model_name", "")).casefold().strip(), powertrain,
            _efficiency_value(vehicle.get("fuel_efficiency_km_per_l")),
            _efficiency_value(vehicle.get("electric_efficiency_km_per_kwh")),
        )
        grouped.setdefault(key, []).append(vehicle)

    representatives: list[dict] = []
    for profiles in grouped.values():
        # Prefer the ordinary/lowest-price representative, then stable name.
        representative = min(profiles, key=lambda item: (
            item.get("purchase_price_ntd") is None,
            item.get("purchase_price_ntd") or 0,
            "選" in str(item.get("trim_name", "")),
            str(item.get("trim_name", "")),
        ))
        trim_names = [str(item.get("trim_name", "")).strip() for item in profiles if item.get("trim_name")]
        if trim_names:
            # A transient display-only field: selection still sends the trusted
            # representative vehicle ID and re-fetches it server-side.
            representative = {**representative, "display_trim_summary": "、".join(dict.fromkeys(trim_names))}
        representatives.append(representative)
    return representatives


def _efficiency_value(value: object) -> float | None:
    return round(float(value), 3) if isinstance(value, (int, float)) else None


def _vehicle_bubble(vehicle: dict, slot: str) -> dict:
    powertrain = normalize_powertrain(str(vehicle.get("drivetrain", vehicle.get("powertrain", "")))) or ""
    label = f"{_ICONS.get(powertrain, '🚗')} {POWERTRAIN_LABELS.get(powertrain, powertrain)}"
    contents = [{"type": "text", "text": str(vehicle.get("display_name") or vehicle["model_name"]), "weight": "bold", "size": "xl", "wrap": True},
                {"type": "text", "text": label, "size": "sm", "color": "#666666"}]
    if vehicle.get("display_trim_summary") or vehicle.get("trim_name"):
        trim = str(vehicle.get("display_trim_summary") or vehicle.get("trim_name"))
        contents.append({"type": "text", "text": f"等級：{trim}", "size": "xs", "color": "#666666", "wrap": True, "margin": "sm"})
    fuel, electric = vehicle.get("fuel_efficiency_km_per_l"), vehicle.get("electric_efficiency_km_per_kwh")
    if isinstance(fuel, (int, float)):
        contents += [{"type": "separator", "margin": "md"}, {"type": "text", "text": "官方平均油耗", "size": "xs", "color": "#888888"}, {"type": "text", "text": f"{float(fuel):g} km/L", "weight": "bold"}]
    if isinstance(electric, (int, float)):
        contents += [{"type": "separator", "margin": "md"}, {"type": "text", "text": "官方平均電耗", "size": "xs", "color": "#888888"}, {"type": "text", "text": f"{float(electric):g} km/kWh", "weight": "bold"}]
    if isinstance(vehicle.get("purchase_price_ntd"), (int, float)):
        contents.append({"type": "text", "text": f"NT$ {float(vehicle['purchase_price_ntd']):,.0f}", "weight": "bold", "margin": "md"})
    bubble = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": contents}, "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "button", "style": "primary", "action": {"type": "postback", "label": "選這台", "data": f"action=select_vehicle&slot={slot}&vehicle_id={vehicle['id']}"}}]}}
    if vehicle.get("image_url"):
        bubble["hero"] = {"type": "image", "url": vehicle["image_url"], "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"}
    return bubble
