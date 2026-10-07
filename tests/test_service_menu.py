from app.services.cost_flow import cost_flow_manager
from app.services.event_processor import EventProcessor, flow_scope
from app.services.ev_fit_flow import ev_fit_manager
from app.services.service_menu_flex import build_service_menu_flex


def test_service_menu_has_four_postback_entry_points() -> None:
    menu = build_service_menu_flex()
    cards = menu["contents"]["contents"]
    assert len(cards) == 4
    actions = {card["footer"]["contents"][0]["action"]["data"] for card in cards}
    assert actions == {
        "action=start_ev_fit", "action=start_cost_compare",
        "action=start_vehicle_recommendation", "action=open_ev_question_help",
    }


class _Client:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.combined: list[tuple[str, dict]] = []
        self.quick: list[str] = []

    def reply_text(self, _token: str, text: str) -> None:
        self.text.append(text)

    def reply_text_and_flex(self, _token: str, text: str, flex: dict) -> None:
        self.combined.append((text, flex))

    def reply_text_with_quick_replies(self, _token: str, text: str, _items: list[dict]) -> None:
        self.quick.append(text)

    def reply_flex(self, _token: str, _flex: dict) -> None:
        self.text.append("flex")


class _Repository:
    def __init__(self) -> None:
        self.seen = False
        self.marked = 0

    def claim_event(self, _event_id: str) -> bool: return True
    def touch_group(self, _group: str) -> str: return "group-db"
    def get_knowledge_source(self, _source: str): return None
    def record_group_signal(self, *_args: object) -> bool: return False
    def member_needs_onboarding(self, *_args: object) -> bool: return not self.seen
    def mark_member_onboarded(self, *_args: object) -> None:
        self.seen = True; self.marked += 1


def _message(event_id: str, user_id: str, text: str) -> dict:
    return {"webhookEventId": event_id, "type": "message", "replyToken": event_id,
            "source": {"type": "group", "groupId": "G-menu", "userId": user_id},
            "message": {"type": "text", "text": text}}


def _postback(event_id: str, user_id: str, action: str) -> dict:
    return {"webhookEventId": event_id, "type": "postback", "replyToken": event_id,
            "source": {"type": "group", "groupId": "G-menu", "userId": user_id},
            "postback": {"data": f"action={action}"}}


def test_menu_alias_and_help_text_reopen_the_flex_menu() -> None:
    client = _Client(); processor = EventProcessor(line_client=client, repository=_Repository())
    processor.process([_message("alias", "B", "@電車解惑所"), _message("help", "B", "功能")])
    assert len(client.combined) == 2
    assert all("我在" in text for text, _flex in client.combined)


def test_first_ev_question_answers_then_shows_onboarding_once() -> None:
    client = _Client(); repository = _Repository(); processor = EventProcessor(line_client=client, repository=repository)
    processor.process([_message("first", "B", "bZ4X 電池可以用多久？")])
    assert "電池" in client.combined[0][0]
    assert client.combined[0][1]["altText"] == "第一次使用的功能入口"
    processor.process([_message("second", "B", "電池可以用多久？")])
    assert repository.marked == 1
    assert len(client.combined) == 1


def test_history_menu_actions_start_separate_owner_sessions() -> None:
    client = _Client(); processor = EventProcessor(line_client=client, repository=_Repository())
    cost = _postback("cost-A", "A", "start_cost_compare")
    fit = _postback("fit-B", "B", "start_ev_fit")
    processor.process([cost, fit])
    assert cost_flow_manager.is_active(flow_scope(cost["source"]))
    assert ev_fit_manager.is_active(flow_scope(fit["source"]))
