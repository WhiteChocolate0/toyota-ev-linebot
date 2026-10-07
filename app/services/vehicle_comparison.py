"""Up-to-three vehicle specification/needs comparison; TCO remains two-car."""
from dataclasses import dataclass, field
from datetime import UTC, datetime

DIMENSIONS = (("價格", "purchase_price_ntd"), ("動力形式", "drivetrain"), ("能源效率", "energy_efficiency"),
              ("座位", "seats"), ("已驗證空間資訊", "cargo_capacity_l"), ("官方續航", "range_km"),
              ("充電需求", "charging_requirement"), ("保固／電池資訊", "warranty"))

@dataclass
class VehicleComparisonSession:
    vehicle_ids: list[str] = field(default_factory=list)
    profiles: list[dict] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=lambda: [key for _, key in DIMENSIONS])
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

class VehicleComparisonManager:
    def __init__(self): self._sessions: dict[str, VehicleComparisonSession] = {}
    def get(self, scope: str) -> VehicleComparisonSession | None: return self._sessions.get(scope)
    def set_profiles(self, scope: str, profiles: list[dict]) -> tuple[VehicleComparisonSession, bool]:
        session = self._sessions.setdefault(scope, VehicleComparisonSession())
        # Catalog rows always have IDs; model-name fallback keeps older test and
        # migration-compatible callers usable without creating empty sessions.
        unique = list(dict.fromkeys(str(item.get("id") or item.get("model_name")) for item in profiles if item.get("id") or item.get("model_name")))
        if len(unique) > 3: return session, True
        session.vehicle_ids = unique; session.profiles = [item for item in profiles if str(item.get("id") or item.get("model_name")) in unique]; session.updated_at = datetime.now(UTC)
        return session, False
    def remove(self, scope: str, vehicle_id: str) -> VehicleComparisonSession | None:
        session = self.get(scope)
        if not session: return None
        session.vehicle_ids = [item for item in session.vehicle_ids if item != vehicle_id]
        session.profiles = [item for item in session.profiles if str(item.get("id")) != vehicle_id]; session.updated_at = datetime.now(UTC)
        return session

def comparison_text(session: VehicleComparisonSession, profile: object | None = None) -> str:
    priorities = ["已驗證空間資訊", "價格", "能源效率"] if getattr(profile, "cargo_space_priority", None) or "cost" in getattr(profile, "priority_factors", set()) else []
    ordered = [pair for pair in DIMENSIONS if pair[0] in priorities] + [pair for pair in DIMENSIONS if pair[0] not in priorities]
    header = "【你現在比較的 " + str(len(session.profiles)) + " 台】\n" + "、".join(str(item.get("model_name")) for item in session.profiles)
    parts = [header]
    for label, key in ordered:
        rows = []
        for item in session.profiles:
            value = item.get(key)
            if key == "purchase_price_ntd" and value is not None: value = f"NT$ {value:,.0f}"
            if key == "cargo_capacity_l" and value is not None: value = f"{value} L"
            rows.append(f"{item.get('model_name')}：{value if value not in (None, '') else '官方未提供／目前無資料'}")
        parts.append("\n" + label + "\n" + "\n".join(rows))
    return "\n".join(parts)

def build_comparison_flex(session: VehicleComparisonSession, profile: object | None = None) -> dict:
    text = comparison_text(session, profile)
    pair_buttons = []
    for left in range(len(session.vehicle_ids)):
        for right in range(left + 1, len(session.vehicle_ids)):
            pair_buttons.append({"type": "button", "style": "secondary", "action": {"type": "postback", "label": "選這兩台算完整成本", "data": f"action=comparison_cost_pair&a={session.vehicle_ids[left]}&b={session.vehicle_ids[right]}"}})
    return {"type": "flex", "altText": "車款比較", "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": text, "wrap": True, "size": "sm"}]}, "footer": {"type": "box", "layout": "vertical", "contents": pair_buttons}}}

vehicle_comparison_manager = VehicleComparisonManager()
