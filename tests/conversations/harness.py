"""Black-box harness around the real EventProcessor used by conversation tests."""

from __future__ import annotations

import json
from dataclasses import asdict

from app.services.comparison_context import comparison_context_manager
from app.services.conversation_context import conversation_context_manager
from app.services.cost_flow import cost_flow_manager
from app.services.ev_fit_flow import ev_fit_manager
from app.services.event_processor import EventProcessor, flow_scope
from app.services.mileage_parser import MileageParser
from app.services.recommendation_engine import recommendation_engine
from app.services.vehicle_comparison import vehicle_comparison_manager

from .scenarios import Turn


class RecordingLineClient:
    def __init__(self) -> None:
        self.replies: list[str] = []

    def reply_text(self, _token: str, text: str) -> None:
        self.replies.append(text)

    def reply_texts(self, _token: str, texts: list[str]) -> None:
        self.replies.extend(texts)

    def reply_text_with_quick_replies(self, _token: str, text: str, _items: list[dict]) -> None:
        self.replies.append(text)

    def reply_text_and_flex(self, _token: str, text: str, flex: dict) -> None:
        # The accompanying text is the primary user-facing answer.  Menu JSON
        # must not be mistaken for bot prose by UX assertions.
        self.replies.append(text)

    def reply_flex(self, _token: str, flex: dict) -> None:
        # A Flex reply has no plain-text fallback in the processor, so expose
        # its rendered text nodes—not raw JSON—to the assertion layer.
        def text_nodes(value: object) -> list[str]:
            if isinstance(value, dict):
                result = [str(value["text"])] if isinstance(value.get("text"), str) else []
                for child in value.values(): result.extend(text_nodes(child))
                return result
            if isinstance(value, list): return [part for child in value for part in text_nodes(child)]
            return []
        self.replies.append("\n".join(dict.fromkeys(text_nodes(flex))))

    def reply_group_welcome(self, _token: str) -> None:
        self.replies.append("歡迎使用電車解惑所")

    def show_loading_animation(self, _user_id: str, seconds: int = 5) -> None:
        pass


class NoopRewriter:
    """Keep a deployment regression deterministic and offline."""
    is_enabled = False

    def rewrite_vehicle_reply(self, *, fallback: str, **_kwargs: object) -> str:
        return fallback


class ScenarioRepository:
    """Deterministic source/catalogue fixture; no network or production DB required."""

    def __init__(self) -> None:
        self.context_rows: dict[tuple[str | None, str], dict] = {}
        self.profiles = [
            {"id": "bz4x-id", "model_name": "bZ4X", "model_year": 2025, "trim_name": None, "drivetrain": "ev", "aliases": ["bz4x"], "purchase_price_ntd": 1_280_000, "electric_efficiency_km_per_kwh": 6.7, "source_url": "https://example.com/bz4x"},
            {"id": "rav4-id", "model_name": "RAV4", "model_year": 2025, "trim_name": None, "drivetrain": "hybrid", "aliases": ["rav 4"], "purchase_price_ntd": 1_120_000, "fuel_efficiency_km_per_l": 20.0, "source_url": "https://example.com/rav4"},
            {"id": "cc-hev-id", "model_name": "COROLLA CROSS", "model_year": 2025, "trim_name": "Hybrid", "drivetrain": "hybrid", "aliases": ["corolla cross hybrid", "corolla cross"], "purchase_price_ntd": 900_000, "fuel_efficiency_km_per_l": 23.5, "source_url": "https://example.com/cc"},
            {"id": "yaris-id", "model_name": "YARIS CROSS", "model_year": 2025, "trim_name": None, "drivetrain": "gasoline", "aliases": ["yaris cross"], "purchase_price_ntd": 720_000, "fuel_efficiency_km_per_l": 15.0, "source_url": "https://example.com/yaris"},
            {"id": "altis-id", "model_name": "ALTIS", "model_year": 2025, "trim_name": None, "drivetrain": "hybrid", "aliases": ["altis"], "purchase_price_ntd": 850_000, "fuel_efficiency_km_per_l": 24.0, "source_url": "https://example.com/altis"},
        ]

    def claim_event(self, _event_id: str) -> bool: return True
    def touch_group(self, _group_id: str) -> str: return "group-db-id"
    def list_active_vehicle_profiles(self) -> list[dict]: return self.profiles
    def get_active_vehicle_profile_by_id(self, vehicle_id: str) -> dict | None: return next((p for p in self.profiles if p["id"] == vehicle_id), None)
    def get_vehicle_feature(self, model: str, feature: str) -> dict | None:
        return {"description": "bZ4X 可使用一般家用 110V 插座補電"} if (model, feature) == ("bZ4X", "HOME_110V_CHARGING") else None
    def get_knowledge_source(self, _source_id: str) -> dict:
        return {"title": "官方測試來源", "url": "https://example.com/official", "publisher": "TOYOTA Taiwan", "verified_at": "2026-09-01"}
    def get_conversation_context(self, group_id, user_id): return self.context_rows.get((group_id, user_id))
    def save_conversation_context(self, group_id, user_id, context, expires_at) -> bool:
        self.context_rows[(group_id, user_id)] = {"context_json": context, "expires_at": expires_at}; return True
    def record_concern(self, *_args): pass
    def record_group_signal(self, *_args): return False
    def cancel_active_conversation_flows(self, *_args): return True
    def cancel_vehicle_comparison_session(self, *_args): return True


def reset_shared_state() -> None:
    """Managers are process singletons in production; isolate every scenario."""
    for manager, names in (
        (cost_flow_manager, ("_states", "_group_owners")),
        (ev_fit_manager, ("_states",)),
        (conversation_context_manager, ("_contexts",)),
        (comparison_context_manager, ("_contexts",)),
        (vehicle_comparison_manager, ("_sessions",)),
        (recommendation_engine, ("_profiles",)),
    ):
        for name in names:
            value = getattr(manager, name, None)
            if isinstance(value, dict): value.clear()


class ConversationHarness:
    def __init__(self) -> None:
        reset_shared_state()
        self.client = RecordingLineClient()
        self.repository = ScenarioRepository()
        self.processor = EventProcessor(
            line_client=self.client, repository=self.repository,
            rewriter=NoopRewriter(), parser=MileageParser(api_key=""),
        )
        self.sequence = 0

    @staticmethod
    def active_flow(source: dict) -> str | None:
        scope = flow_scope(source)
        if cost_flow_manager.is_active(scope): return f"COST_CALCULATION:{cost_flow_manager.current_stage(scope)}"
        if ev_fit_manager.is_active(scope): return f"EV_FIT"
        return None

    def send(self, turn: Turn) -> dict[str, object]:
        self.sequence += 1
        source = {"type": turn.source_type, "userId": turn.sender_id}
        if turn.source_type == "group": source["groupId"] = "conversation-regression-group"
        before_reply_count = len(self.client.replies)
        flow_before = self.active_flow(source)
        event = {"webhookEventId": f"conversation-{self.sequence}", "type": "message", "replyToken": f"reply-{self.sequence}", "source": source, "message": {"type": "text", "text": turn.messages}}
        self.processor.process([event])
        reply = "\n".join(self.client.replies[before_reply_count:])
        scope = flow_scope(source)
        context = conversation_context_manager.get(scope)
        return {
            "reply": reply, "flow_before": flow_before, "flow_after": self.active_flow(source),
            "context": asdict(context) if context else {}, "previous_replies": self.client.replies[:before_reply_count],
        }
