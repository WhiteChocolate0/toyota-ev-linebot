"""Rule-based response routing for the first safe conversational release."""

from dataclasses import dataclass

from app.services.concern_classifier import IntentClassification, classify_concern
from app.services.faq_templates import FAQ_TEMPLATES
from app.services.message_preprocessor import normalize_bot_reference
from app.services.internal_concern_priorities import EXPLORATION_OPTIONS


@dataclass(frozen=True)
class RoutedReply:
    text: str
    concern_code: str | None = None
    classification: IntentClassification | None = None
    quick_replies: list[dict] | None = None


QUESTION_MARKERS = (
    "?", "？", "嗎", "怎麼", "如何", "請問", "多少", "能不能", "可以嗎",
    "為什麼", "多久", "幾年", "是不是", "有沒有", "值不值得", "好不好",
)


def route_text_message(text: str, source_type: str) -> RoutedReply | None:
    prepared = normalize_bot_reference(text)
    if prepared.is_bot_invocation:
        return RoutedReply("我在 🙋‍♀️ 有什麼想問的？", "BOT_INVOCATION")
    if not prepared.text:
        return None
    normalized = prepared.text
    lowered = normalized.lower()

    uncertain_ev = any(phrase in normalized for phrase in ("不確定要不要買電車", "對電車有點擔心", "不知道該注意什麼", "不知道要注意什麼", "不確定電車"))
    if source_type == "user" and uncertain_ev:
        items = [{"type": "action", "action": {"type": "message", "label": label, "text": text}} for label, text in EXPLORATION_OPTIONS]
        return RoutedReply("你比較在意哪一塊？如果還不確定，可以先從充電、電池、續航和成本幾個面向一起看。", "EV_GENERAL_OPINION", classify_concern(normalized), items)

    if normalized == "我們先自己聊":
        return RoutedReply("沒問題，我會先安靜待命；需要 TOYOTA 電動車相關解惑時再叫我就好。")
    if "成本試算" in normalized:
        intent = classify_concern(normalized)
        return RoutedReply(FAQ_TEMPLATES["CALCULATOR"], "CALCULATOR", intent)
    if "生活健檢" in normalized or "適合開電動車" in normalized or "生活適合 ev" in lowered:
        intent = classify_concern(normalized)
        return RoutedReply(FAQ_TEMPLATES["EV_FIT"], "EV_FIT", intent)
    if "問 ev 問題" in lowered or normalized == "我想問問題":
        return RoutedReply("可以直接問我 TOYOTA 電動車的電池、充電、成本、安全或保養問題；我會先提供可確認的方向。")

    concern = classify_concern(normalized)
    if not concern.relevant or not concern.should_reply:
        return None
    return RoutedReply(FAQ_TEMPLATES.get(concern.topic, FAQ_TEMPLATES["UNKNOWN_RELEVANT"]), concern.topic, concern)
