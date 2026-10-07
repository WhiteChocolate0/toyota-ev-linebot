"""Privacy-first signals used to support, never profile, a LINE group."""

from dataclasses import dataclass

from app.services.concern_classifier import classify_concern


@dataclass(frozen=True)
class GroupSignal:
    topic: str
    relevant: bool
    stance: str
    labels: tuple[str, ...]
    level: str


_NEGATIVE = ("不想", "不要", "擔心", "怕", "太貴", "麻煩", "不方便", "焦慮", "不敢")
_POSITIVE = ("可以", "適合", "省", "好處", "想買", "值得", "方便")


def analyse_group_message(text: str) -> GroupSignal:
    """Return only a transient, non-sensitive EV discussion signal.

    No relationship, age, gender, or raw message text is returned or persisted.
    """
    intent = classify_concern(text)
    if not intent.relevant:
        return GroupSignal("UNRELATED", False, "neutral", (), "L0")
    lowered = text.lower()
    negative = any(word in text for word in _NEGATIVE)
    positive = any(word in text for word in _POSITIVE)
    stance = "concerned" if negative else "positive" if positive else "neutral"
    labels: list[str] = []
    if intent.topic in {"COST", "CALCULATOR", "RESALE"}:
        labels.append("cost_focused")
    if intent.topic in {"BATTERY", "SAFETY"}:
        labels.append("safety_focused")
    if negative:
        labels.append("skeptical")
    if positive:
        labels.append("ev_positive")
    if any(word in text for word in ("決定", "選哪台", "要不要買", "怎麼選")):
        labels.append("decision_maker_candidate")
    # L1 and L2 retain the existing explicit-invocation/question behaviour;
    # L3 is only a trackable discussion statement and never judges a person.
    asks = any(marker in text for marker in ("?", "？", "嗎", "怎麼", "如何", "請問", "能不能", "可以嗎", "多少", "多久", "幾年", "什麼", "為何", "為什麼"))
    level = "L1" if "@" in text or "電車解惑所" in text else "L2" if asks else "L3"
    return GroupSignal(intent.topic, True, stance, tuple(dict.fromkeys(labels)), level)


TOPIC_NAMES = {
    "CHARGING": "住家／外出充電條件", "BATTERY": "電池壽命與保固", "COST": "用車成本",
    "CALCULATOR": "成本試算", "SAFETY": "安全性", "RANGE": "續航與長途使用",
    "RESALE": "殘值", "EV_FIT": "生活適配", "VEHICLE_COMPARISON": "車款比較",
}


def topic_name(topic: str) -> str:
    return TOPIC_NAMES.get(topic, "EV 用車條件")
