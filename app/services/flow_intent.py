"""Global intent routing used before a state-specific parser."""

import re
from dataclasses import dataclass

from app.services.charging_parser import charging_parser
from app.services.mileage_parser import mileage_parser
from app.services.powertrain import parse_powertrain


@dataclass(frozen=True)
class FlowIntent:
    intent: str
    payload: object | None = None


def route_flow_intent(text: str) -> FlowIntent:
    normalized = text.strip()
    compact = normalized.replace(" ", "").lower()
    if compact in {"取消", "取消試算", "停止", "結束"}:
        return FlowIntent("cancel")
    if compact in {"重新開始", "重來", "restart"}:
        return FlowIntent("restart")
    # Global routing is intentionally narrow.  Field parsers must never compete
    # here: "電" belongs to the powertrain state, and "Altis" to model state.
    if any(word in normalized for word in ("我要換車", "我要改車", "改車款", "換車款")):
        return FlowIntent("vehicle_change")
    if any(word in normalized for word in ("實際油耗", "實際電耗", "使用實際", "我要用實際")):
        return FlowIntent("actual_efficiency")
    if re.search(r"(?:持有|使用|開)\s*\d+\s*年|^\d+\s*年$", normalized):
        return FlowIntent("ownership_years")
    if any(marker in normalized for marker in ("幫助", "說明", "help")):
        return FlowIntent("ask_question")
    return FlowIntent("answer_current_field")
