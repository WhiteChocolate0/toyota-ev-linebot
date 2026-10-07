"""Helpers that mirror LINE webhook event shapes."""

from __future__ import annotations

from itertools import count

_ids = count(1)


def _source(user_id: str, source_type: str, group_id: str | None) -> dict:
    source = {"type": source_type, "userId": user_id}
    if source_type == "group": source["groupId"] = group_id or "G_TEST"
    return source


def make_text_event(user_id: str, message: str, source_type: str = "user", group_id: str | None = None) -> dict:
    event_id = f"test-message-{next(_ids)}"
    return {"webhookEventId": event_id, "type": "message", "replyToken": event_id,
            "source": _source(user_id, source_type, group_id), "message": {"type": "text", "id": event_id, "text": message}}


def make_postback_event(user_id: str, data: str, source_type: str = "user", group_id: str | None = None) -> dict:
    event_id = f"test-postback-{next(_ids)}"
    return {"webhookEventId": event_id, "type": "postback", "replyToken": event_id,
            "source": _source(user_id, source_type, group_id), "postback": {"data": data}}


def make_follow_event(user_id: str = "U_TEST") -> dict:
    event_id = f"test-follow-{next(_ids)}"
    return {"webhookEventId": event_id, "type": "follow", "replyToken": event_id, "source": _source(user_id, "user", None)}


def make_join_event(group_id: str = "G_TEST", user_id: str = "U_TEST") -> dict:
    event_id = f"test-join-{next(_ids)}"
    return {"webhookEventId": event_id, "type": "join", "replyToken": event_id, "source": _source(user_id, "group", group_id)}
