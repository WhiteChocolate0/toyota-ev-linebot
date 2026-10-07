"""Privacy-preserving family concern board: issues, never people or chat text."""
from datetime import UTC, datetime, timedelta
from app.services.internal_concern_priorities import concern_priority_rank

CATEGORIES = {"BATTERY", "CHARGING", "RANGE", "COST", "MAINTENANCE", "SAFETY", "RESALE", "SPACE", "LONG_TRIP", "BRAND_TRUST", "TAX_POLICY"}
TOPIC_MAP = {"CALCULATOR": "COST", "POLICY": "TAX_POLICY", "TOYOTA_BRAND": "BRAND_TRUST", "TRUNK_SPACE": "SPACE", "VEHICLE_SPACE": "SPACE", "USAGE_SCENARIO": "LONG_TRIP"}
STATUS_ICON = {"CLARIFIED": "✅", "NEEDS_VERIFICATION": "⚠️", "DISAGREEMENT": "⚖️", "OPEN": "❓"}
LABELS = {"BATTERY": "電池", "CHARGING": "家庭充電", "RANGE": "續航", "COST": "使用成本", "MAINTENANCE": "保養", "SAFETY": "安全", "RESALE": "殘值", "SPACE": "空間", "LONG_TRIP": "長途使用", "BRAND_TRUST": "品牌信任", "TAX_POLICY": "稅務／政策"}

def concern_type(topic: str) -> str | None:
    value = TOPIC_MAP.get(topic, topic)
    return value if value in CATEGORIES else None

def status_from_signal(topic: str, stance: str) -> str:
    if stance == "concerned": return "OPEN"
    return "NEEDS_VERIFICATION" if topic in {"CHARGING", "RANGE", "RESALE", "TAX_POLICY"} else "OPEN"

def build_concern_board(rows: list[dict]) -> str:
    active = [row for row in rows if not row.get("expires_at") or row["expires_at"] > datetime.now(UTC).isoformat()]
    if not active: return "【目前討論進度】\n目前尚未留下需要追蹤的 EV 議題。"
    rank_map = {"CHARGING": concern_priority_rank("CHARGING_CONVENIENCE"), "BATTERY": concern_priority_rank("BATTERY_LIFE"), "COST": concern_priority_rank("PURCHASE_PRICE"), "MAINTENANCE": concern_priority_rank("MAINTENANCE"), "RANGE": concern_priority_rank("RANGE"), "SAFETY": concern_priority_rank("SAFETY"), "RESALE": concern_priority_rank("RESALE")}
    active.sort(key=lambda row: (rank_map.get(row.get("concern_type"), 999), str(row.get("concern_type", ""))))
    lines = ["【目前討論進度】"]
    for row in active:
        status, key = row.get("status", "OPEN"), row.get("concern_type", "EV")
        label = LABELS.get(key, key)
        note = {"CLARIFIED": "已完成可查證說明", "NEEDS_VERIFICATION": "尚待確認條件或官方資料", "DISAGREEMENT": "目前仍有不同看法", "OPEN": "目前仍有疑問"}.get(status, "目前仍有疑問")
        lines.append(f"{STATUS_ICON.get(status, '❓')} {label}\n{note}")
    counts = {status: sum(1 for row in active if row.get("status") == status) for status in STATUS_ICON}
    lines.append(f"\n已釐清：{counts['CLARIFIED']}｜待確認：{counts['NEEDS_VERIFICATION']}｜尚有分歧：{counts['DISAGREEMENT']}")
    lines.append("下一步：優先確認仍標示為待確認的用車條件；需要時再進行完整 TCO 比較。")
    return "\n".join(lines)
