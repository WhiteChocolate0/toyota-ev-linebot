"""Short-lived structured context; Supabase, not memory, is authoritative."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.services.powertrain import BEV, HEV


@dataclass
class ConversationContext:
    active_domain: str = "vehicle"
    active_topic: str | None = None
    active_goal: str | None = None
    active_vehicle_id: str | None = None
    mentioned_vehicle_ids: list[str] = field(default_factory=list)
    selected_vehicle_ids: list[str] = field(default_factory=list)
    pending_comparison: bool = False
    slots: dict[str, object] = field(default_factory=dict)
    last_intent: str | None = None
    last_bot_action: str | None = None
    last_active_flow: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=30))

    @classmethod
    def from_row(cls, row: dict[str, object]) -> "ConversationContext":
        data = row.get("context_json", row)
        data = data if isinstance(data, dict) else {}
        now = datetime.now(UTC)
        def stamp(name: str, fallback: datetime) -> datetime:
            value = row.get(name, data.get(name))
            if isinstance(value, datetime): return value.astimezone(UTC)
            if isinstance(value, str):
                try: return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
                except ValueError: pass
            return fallback
        return cls(
            active_domain=str(data.get("active_domain") or "vehicle"), active_topic=data.get("active_topic") if isinstance(data.get("active_topic"), str) else None,
            active_goal=data.get("active_goal") if isinstance(data.get("active_goal"), str) else None, active_vehicle_id=data.get("active_vehicle_id") if isinstance(data.get("active_vehicle_id"), str) else None,
            mentioned_vehicle_ids=[str(item) for item in data.get("mentioned_vehicle_ids", []) if item], selected_vehicle_ids=[str(item) for item in data.get("selected_vehicle_ids", []) if item],
            pending_comparison=bool(data.get("pending_comparison", False)), slots=dict(data.get("slots", {})) if isinstance(data.get("slots"), dict) else {},
            last_intent=data.get("last_intent") if isinstance(data.get("last_intent"), str) else None, last_bot_action=data.get("last_bot_action") if isinstance(data.get("last_bot_action"), str) else None,
            last_active_flow=data.get("last_active_flow") if isinstance(data.get("last_active_flow"), str) else None, updated_at=stamp("updated_at", now), expires_at=stamp("expires_at", now),
        )

    def payload(self) -> dict[str, object]:
        return {key: value for key, value in vars(self).items() if key not in {"updated_at", "expires_at"}}

    def clear_expired_semantics(self) -> None:
        # Flow state belongs to conversation_flows and must not be cleared here.
        self.active_domain = "vehicle"; self.active_topic = self.active_goal = self.active_vehicle_id = None
        self.mentioned_vehicle_ids.clear(); self.selected_vehicle_ids.clear(); self.pending_comparison = False
        self.slots.clear(); self.last_intent = None


@dataclass(frozen=True)
class ContextResolution:
    topic: str | None
    goal: str | None
    slots: dict[str, object]
    resolved_using_context: bool
    inherited_topic: bool = False
    inherited_entities: bool = False
    resolved_by: str = "ELLIPSIS"


class ConversationContextManager:
    _ttl = timedelta(minutes=30)

    def __init__(self) -> None:
        self._contexts: dict[str, ConversationContext] = {}

    def get(self, scope_id: str) -> ConversationContext | None:
        context = self._contexts.get(scope_id)
        if context and context.expires_at <= datetime.now(UTC):
            context.clear_expired_semantics(); self._contexts.pop(scope_id, None)
            return None
        return context

    def hydrate(self, scope_id: str, row: dict[str, object] | None) -> tuple[ConversationContext, str]:
        """Load a valid cache entry, otherwise hydrate one DB row for this request."""
        cached = self.get(scope_id)
        if cached: return cached, "MEMORY"
        if row:
            context = ConversationContext.from_row(row)
            if context.expires_at > datetime.now(UTC):
                self._contexts[scope_id] = context
                return context, "DATABASE"
        context = ConversationContext()
        self._contexts[scope_id] = context
        return context, "EMPTY"

    def update(self, scope_id: str, *, topic: str | None = None, goal: str | None = None, slots: dict[str, object] | None = None, vehicle_ids: list[str] | None = None, entity_operation: str = "REPLACE", intent: str | None = None, active_vehicle_id: str | None = None) -> ConversationContext:
        context = self._contexts.setdefault(scope_id, ConversationContext())
        # An explicit topic replaces inherited context; otherwise enrich it.
        if topic: context.active_topic = topic
        if goal: context.active_goal = goal
        if slots: context.slots.update({key: value for key, value in slots.items() if value is not None})
        if vehicle_ids is not None:
            ids = list(dict.fromkeys(vehicle_ids))
            if entity_operation == "ADD": context.mentioned_vehicle_ids = list(dict.fromkeys(context.mentioned_vehicle_ids + ids))
            elif entity_operation == "REMOVE": context.mentioned_vehicle_ids = [item for item in context.mentioned_vehicle_ids if item not in ids]
            elif entity_operation == "RESET": context.mentioned_vehicle_ids = []; context.selected_vehicle_ids = []
            else:
                context.mentioned_vehicle_ids = ids
                if len(ids) > 1: context.selected_vehicle_ids = ids
            if len(context.mentioned_vehicle_ids) == 1: context.active_vehicle_id = context.mentioned_vehicle_ids[0]
        if active_vehicle_id: context.active_vehicle_id = active_vehicle_id
        if intent: context.last_intent = intent
        context.updated_at = datetime.now(UTC); context.expires_at = context.updated_at + self._ttl
        return context

    def resolve(self, scope_id: str, text: str) -> ContextResolution | None:
        context = self.get(scope_id)
        if not context:
            return None
        # A newly-created empty cache entry is not context. Explicit messages
        # must proceed to normal routing instead of being mistaken for a
        # continuation merely because they mention an EV powertrain.
        if not (context.active_topic or context.active_goal or context.active_vehicle_id or context.mentioned_vehicle_ids or context.slots):
            return None
        compact = text.replace(" ", "").lower().rstrip("？?")
        if compact in {"多少錢", "多少", "車價多少", "車價呢", "售價呢", "價格呢", "那價格呢", "定價多少", "這台多少", "這台多少錢", "賣多少", "要多少錢"} and context.active_vehicle_id:
            return ContextResolution("VEHICLE_PRICE", "LEARN", dict(context.slots), True, inherited_entities=True, resolved_by="PRICE_FOLLOWUP")
        if any(word in compact for word in ("哪台比較省", "誰比較省", "哪個比較省")) and len(context.mentioned_vehicle_ids) >= 2:
            return ContextResolution("COST", "COMPARE", dict(context.slots), True, inherited_entities=True)
        if compact in {"那後車廂呢", "空間呢", "那空間"} and context.mentioned_vehicle_ids:
            return ContextResolution("TRUNK_SPACE", "COMPARE" if len(context.mentioned_vehicle_ids) >= 2 else "LEARN", dict(context.slots), True, inherited_entities=True)
        explicit_battery = any(word in text for word in ("電池", "安全", "保固"))
        if explicit_battery:
            return ContextResolution("BATTERY", "LEARN", {}, False)
        powertrain = BEV if any(word in text for word in ("電車", "電動車", "純電")) else HEV if "油電" in text else None
        recommendation = any(word in text for word in ("哪台", "哪一台", "比較適合", "推薦"))
        ellipsis = powertrain is not None or recommendation or compact in {"那這台呢？", "那這台呢", "另一台呢？", "另一台呢", "那空間呢？", "那空間呢"}
        if not ellipsis:
            return None
        slots = dict(context.slots)
        if powertrain: slots["powertrain"] = powertrain
        return ContextResolution(
            context.active_topic, "RECOMMEND" if recommendation else context.active_goal,
            slots, True, inherited_topic=context.active_topic is not None,
            inherited_entities=bool(context.mentioned_vehicle_ids),
        )

    def clear(self, scope_id: str) -> None:
        self._contexts.pop(scope_id, None)


conversation_context_manager = ConversationContextManager()
