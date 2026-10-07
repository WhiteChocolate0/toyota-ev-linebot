from app.services.event_processor import EventProcessor
from app.services.group_intelligence import analyse_group_message


def test_unrelated_chat_is_l0_and_has_no_labels() -> None:
    signal = analyse_group_message("晚餐吃什麼")
    assert signal.level == "L0"
    assert signal.labels == ()


def test_ev_concern_is_metadata_only_l3_signal() -> None:
    signal = analyse_group_message("我覺得電動車充電太麻煩")
    assert signal.level == "L3"
    assert signal.topic == "CHARGING"
    assert "skeptical" in signal.labels


class _Client:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.quick: list[tuple[str, list[dict]]] = []

    def reply_text(self, _token: str, text: str) -> None:
        self.replies.append(text)

    def reply_text_with_quick_replies(self, _token: str, text: str, items: list[dict]) -> None:
        self.quick.append((text, items))


class _Repository:
    def __init__(self) -> None:
        self.recorded: list[tuple] = []

    def claim_event(self, _event_id: str) -> bool:
        return True

    def touch_group(self, _line_group_id: str) -> str:
        return "group-id"

    def record_group_signal(self, *values: object) -> bool:
        self.recorded.append(values)
        return False

    def group_summary(self, _group_id: str) -> str:
        return "今天的家庭 EV 討論\n✅ 已釐清：尚無"

    def clear_group_summary(self, _group_id: str, *, delete: bool = False) -> str:
        return "已刪除" if delete else "已重設"


def _event(event_id: str, text: str) -> dict:
    return {"webhookEventId": event_id, "type": "message", "replyToken": event_id,
            "source": {"type": "group", "groupId": "G1", "userId": "U1"},
            "message": {"type": "text", "text": text}}


def test_l3_persists_no_raw_message_and_manual_summary_has_controls() -> None:
    client, repository = _Client(), _Repository()
    processor = EventProcessor(line_client=client, repository=repository)
    raw = "我覺得電動車充電太麻煩"
    processor.process([_event("signal", raw)])
    assert repository.recorded
    assert raw not in repr(repository.recorded)
    processor.process([_event("summary", "整理一下")])
    assert client.quick[-1][0].startswith("【目前討論進度】")
    assert {item["action"]["data"] for item in client.quick[-1][1]} == {"concern_status=CLARIFIED", "concern_status=OPEN", "concern_status=NEEDS_VERIFICATION"}
