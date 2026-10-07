from app.services.concern_classifier import classify_concern
from app.services.message_preprocessor import normalize_bot_reference
from app.services.message_router import route_text_message


def test_bare_bot_alias_is_not_an_ev_query() -> None:
    for text in ("電車解惑所", "@電車解惑所", "解惑所"):
        assert normalize_bot_reference(text).text == ""
        assert normalize_bot_reference(text).is_bot_invocation is True
        assert classify_concern(text).topic == "UNRELATED"
        assert route_text_message(text, "group").concern_code == "BOT_INVOCATION"


def test_bot_invocation_gets_a_small_greeting() -> None:
    reply = route_text_message("電車解惑所在嗎？", "group")
    assert reply is not None
    assert reply.concern_code == "BOT_INVOCATION"
    assert reply.text == "我在 🙋‍♀️ 有什麼想問的？"


def test_alias_is_removed_before_real_ev_question_is_classified() -> None:
    normalized = normalize_bot_reference("電車解惑所 電車比較好嗎？")
    assert normalized.text == "電車比較好嗎？"
    assert classify_concern("電車解惑所 電車比較好嗎？").topic == "EV_GENERAL_OPINION"


def test_mention_is_removed_before_battery_question_is_classified() -> None:
    normalized = normalize_bot_reference("@電車解惑所 bZ4X 電池可以用多久？")
    assert normalized.text == "bZ4X 電池可以用多久？"
    assert classify_concern("@電車解惑所 bZ4X 電池可以用多久？").topic == "BATTERY"


def test_bot_name_inside_general_chat_does_not_create_ev_definition() -> None:
    assert route_text_message("我覺得電車解惑所這名字很好笑", "group") is None
