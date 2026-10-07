"""Preference-led vehicle discovery, with short-lived per-user context.

Only compact, structured preferences are retained: never the original family
chat.  This lets short follow-ups such as「建議呢？」inherit their subject.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import re
from typing import Literal

from app.services.concern_classifier import IntentClassification

NeedTopic = Literal[
    "VEHICLE_RECOMMENDATION", "VEHICLE_SPACE", "TRUNK_SPACE", "PASSENGER_SPACE",
    "FAMILY_USE", "VEHICLE_SIZE", "SEAT_REQUIREMENT", "LUGGAGE_REQUIREMENT",
    "USAGE_SCENARIO", "VEHICLE_COMPARISON",
]


@dataclass
class VehicleNeedContext:
    active_topic: NeedTopic
    user_goal: str
    slots: dict[str, object] = field(default_factory=dict)
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=20))


@dataclass(frozen=True)
class VehicleNeedRoute:
    text: str
    classification: IntentClassification
    quick_replies: list[dict]


class VehicleNeedRouter:
    _ttl = timedelta(minutes=20)
    _contexts: dict[str, VehicleNeedContext]

    def __init__(self) -> None:
        self._contexts = {}

    def context_for(self, scope_id: str) -> VehicleNeedContext | None:
        context = self._contexts.get(scope_id)
        if context and context.expires_at <= datetime.now(UTC):
            self._contexts.pop(scope_id, None)
            return None
        return context

    def clear(self, scope_id: str) -> None:
        self._contexts.pop(scope_id, None)

    def route(self, scope_id: str, text: str) -> VehicleNeedRoute | None:
        normalized = text.strip()
        context = self.context_for(scope_id)
        detected_topic = self._topic(normalized)
        inherited = not detected_topic and context and self._is_follow_up(normalized)
        if not detected_topic and not inherited:
            return None

        topic = detected_topic or context.active_topic  # type: ignore[union-attr]
        slots = dict(context.slots) if context else self._empty_slots()
        slots.update({key: value for key, value in self._slots(normalized, topic).items() if value is not None})
        goal = self._goal(normalized, context)
        next_context = VehicleNeedContext(topic, goal, slots, datetime.now(UTC) + self._ttl)
        self._contexts[scope_id] = next_context
        classification = IntentClassification(
            relevant=True, topic=topic, question_type=self._question_type(goal), user_goal=goal,
            slots=slots, confidence=0.95 if detected_topic else 0.88,
            should_reply=True, needs_followup=not self._can_filter(slots),
        )
        return VehicleNeedRoute(self._reply(topic, goal, slots), classification, self._quick_replies(topic, slots))

    @staticmethod
    def _empty_slots() -> dict[str, object]:
        return {key: None for key in (
            "cargo_space", "passenger_space", "seat_count", "budget", "powertrain",
            "daily_mileage", "long_trip_frequency", "home_charging", "family_use",
            "cargo_requirement", "usage_scenario",
        )}

    @staticmethod
    def _topic(text: str) -> NeedTopic | None:
        if any(word in text for word in ("後車廂", "行李廂", "嬰兒車", "大型行李", "行李箱", "載行李")):
            return "TRUNK_SPACE"
        if any(word in text for word in ("露營", "露營用品", "全家出遊")):
            return "LUGGAGE_REQUIREMENT"
        if any(word in text for word in ("五個人", "五人", "四個人", "家庭用", "全家", "後座空間", "乘坐空間")):
            return "PASSENGER_SPACE"
        if any(word in text for word in ("幾人坐", "座位", "七人座", "五人座")):
            return "SEAT_REQUIREMENT"
        if any(word in text for word in ("空間大", "空間", "寬敞")):
            return "VEHICLE_SPACE"
        if any(word in text for word in ("車身尺寸", "車長", "車寬", "車高", "車子大小")):
            return "VEHICLE_SIZE"
        if any(word in text for word in ("車款比較", "兩台", "哪台比較")):
            return "VEHICLE_COMPARISON"
        if any(word in text for word in ("哪台比較適合", "有沒有", "推薦", "想要")):
            return "VEHICLE_RECOMMENDATION"
        if any(word in text for word in ("通勤", "長途", "出遊")):
            return "USAGE_SCENARIO"
        return None

    @staticmethod
    def _is_follow_up(text: str) -> bool:
        return any(word in text for word in ("建議", "哪台", "大小", "電車", "Toyota", "豐田", "比較", "規格", "多大"))

    @staticmethod
    def _goal(text: str, context: VehicleNeedContext | None) -> str:
        if any(word in text for word in ("比較", "哪個", "兩台")):
            return "COMPARE"
        if any(word in text for word in ("想要", "希望", "適合", "推薦", "建議", "有沒有", "哪台")):
            return "RECOMMEND"
        if "電動車的" in text:
            return "COMPARE"
        if any(word in text for word in ("大小", "多大", "容量", "規格")):
            return "SPEC_LOOKUP"
        return context.user_goal if context else "RECOMMEND"

    @staticmethod
    def _question_type(goal: str) -> str:
        return {"RECOMMEND": "recommendation", "COMPARE": "comparison", "SPEC_LOOKUP": "definition"}.get(goal, "recommendation")

    @staticmethod
    def _slots(text: str, topic: NeedTopic) -> dict[str, object]:
        slots: dict[str, object] = {}
        if topic in {"TRUNK_SPACE", "LUGGAGE_REQUIREMENT"}:
            cargo_words = ("大一點", "空間大", "大型", "很多", "後車廂", "行李廂", "行李箱", "嬰兒車", "露營")
            if any(word in text for word in cargo_words):
                slots["cargo_space"] = "large" if any(word in text for word in ("大一點", "空間大", "大型", "很多", "後車廂")) else "important"
        if "嬰兒車" in text:
            slots["cargo_requirement"] = "stroller"
        if "露營" in text:
            slots["usage_scenario"] = "camping"
        if topic in {"PASSENGER_SPACE", "FAMILY_USE", "SEAT_REQUIREMENT"}:
            slots["passenger_space"] = "important"
            slots["family_use"] = True
        if topic == "USAGE_SCENARIO":
            if "長途" in text:
                slots["long_trip_frequency"] = "frequent"
            if "通勤" in text:
                slots["daily_mileage"] = "commute"
        seats = re.search(r"([2-9])\s*個?人(?:坐|座)?", text)
        if seats:
            slots["seat_count"] = int(seats.group(1))
        if "電動車" in text or "純電" in text or "電車" in text:
            slots["powertrain"] = "BEV"
        elif "油電" in text:
            slots["powertrain"] = "HEV"
        elif "油車" in text:
            slots["powertrain"] = "ICE_GASOLINE"
        budget = re.search(r"預算\s*(\d+(?:\.\d+)?)\s*(萬|元)?", text)
        if budget:
            value = float(budget.group(1))
            slots["budget"] = int(value * 10000) if budget.group(2) == "萬" or value < 10000 else int(value)
        return slots

    @staticmethod
    def _can_filter(slots: dict[str, object]) -> bool:
        return bool(slots.get("powertrain") and (slots.get("cargo_space") or slots.get("passenger_space")))

    def _reply(self, topic: NeedTopic, goal: str, slots: dict[str, object]) -> str:
        if self._can_filter(slots):
            kind = "後車廂／行李需求" if topic in {"TRUNK_SPACE", "LUGGAGE_REQUIREMENT"} else "乘坐空間"
            return f"了解，你重視{kind}，而且限定 {slots['powertrain']}。我會先以 SUV／crossover 類型比較車身尺寸、座位配置與官方公布的行李廂資訊；官方未公布容量的車款不會猜測。"
        if topic in {"TRUNK_SPACE", "LUGGAGE_REQUIREMENT"} and goal == "SPEC_LOOKUP":
            return "可以，我會以官方公布的後車廂容量、後座傾倒與車身尺寸比較；沒有公升數的車款會清楚標示未公布。你想限定電動車嗎？"
        if topic == "PASSENGER_SPACE":
            return "可以，我會從乘坐空間與家庭使用幫你篩。平常主要是幾位乘客，是否需要放嬰兒車或大型行李？"
        return "可以，我會從空間需求幫你篩。你比較常放日常採買、大型行李箱、嬰兒車、露營用品，還是全家出遊用品？"

    @staticmethod
    def _quick_replies(topic: NeedTopic, slots: dict[str, object]) -> list[dict]:
        def item(label: str, text: str) -> dict:
            return {"type": "action", "action": {"type": "message", "label": label, "text": text}}
        if not slots.get("powertrain"):
            return [item("只看電動車", "只看電動車"), item("油電／油車也可", "油車油電電動車都可以"), item("先看 Toyota EV", "先看 Toyota EV")]
        if topic in {"TRUNK_SPACE", "LUGGAGE_REQUIREMENT"}:
            return [item("日常採買", "日常採買"), item("大型行李箱", "大型行李箱"), item("嬰兒車", "會載嬰兒車"), item("露營用品", "常常露營")]
        return [item("五人乘坐", "家裡五個人"), item("需要嬰兒車", "會載嬰兒車"), item("直接看車款", "我想知道建議")]


vehicle_need_router = VehicleNeedRouter()
