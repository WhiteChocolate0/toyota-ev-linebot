import json

import pytest

from app.services.concern_classifier import IntentClassifier, classify_concern
from app.services.message_router import route_text_message


@pytest.mark.parametrize(("text", "topic", "question_type"), [
    ("EV 是什麼？", "EV_BASIC", "definition"),
    ("電車比較好嗎？", "EV_GENERAL_OPINION", "evaluation"),
    ("油車還能開", "ICE_FUTURE", "future"),
    ("Toyota 品牌很好嗎？", "TOYOTA_BRAND", "evaluation"),
    ("以後是不是不能買油車", "ICE_FUTURE", "future"),
])
def test_relevant_topics_have_a_valid_reply_decision(text: str, topic: str, question_type: str) -> None:
    result = classify_concern(text)
    assert result.relevant is True
    assert result.topic == topic
    assert result.question_type == question_type
    assert result.should_reply is True


def test_personal_toyota_mention_is_relevant_but_does_not_interrupt_group() -> None:
    result = classify_concern("我爸開 Toyota")
    assert result.relevant is True
    assert result.topic == "TOYOTA_BRAND"
    assert result.should_reply is False
    assert route_text_message("我爸開 Toyota", "group") is None


def test_unrelated_chat_remains_silent() -> None:
    result = classify_concern("晚餐吃什麼")
    assert result.topic == "UNRELATED"
    assert result.should_reply is False
    assert route_text_message("晚餐吃什麼", "group") is None


def test_keyword_fast_path_does_not_need_semantic_model() -> None:
    classifier = IntentClassifier(api_key="", post=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not call model")))
    assert classifier.classify("電池壞掉是不是很貴？").topic == "BATTERY"


@pytest.mark.parametrize(("text", "topic"), [
    ("HEV 是什麼？", "EV_BASIC"),
    ("PHEV 是什麼？", "EV_BASIC"),
    ("PHEV 電池沒電還能開嗎？", "RANGE"),
    ("bZ4X 家裡 110V 能充嗎？", "BZ4X"),
    ("純電車是不是不用保養？", "MAINTENANCE"),
])
def test_acronyms_and_non_question_mark_questions_route_to_the_right_topic(text: str, topic: str) -> None:
    result = classify_concern(text)
    assert result.topic == topic
    assert result.should_reply is True


def test_semantic_classifier_validates_unknown_domain_language() -> None:
    class Response:
        def raise_for_status(self) -> None: pass
        def json(self) -> dict:
            payload = {"relevant": True, "topic": "UNKNOWN_RELEVANT", "question_type": "future", "confidence": 0.77, "should_reply": True, "needs_source": False, "needs_followup": True}
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
    classifier = IntentClassifier(api_key="test", post=lambda *_args, **_kwargs: Response())
    result = classifier.classify("零排放小客車以後會成主流嗎？")
    assert result.topic == "UNKNOWN_RELEVANT"
    assert result.relevant and result.should_reply


def test_relevant_group_statement_without_question_is_not_interrupted() -> None:
    assert route_text_message("我最近在看電動車", "group") is None
