from datetime import UTC, datetime, timedelta

from app.services.conversation_context import ConversationContextManager
from app.services.powertrain import BEV, HEV


def test_topic_inheritance_resolves_electric_vehicle_and_recommendation() -> None:
    manager = ConversationContextManager()
    manager.update("A", topic="TRUNK_SPACE", goal="RECOMMEND", slots={"cargo_space": "large"})
    electric = manager.resolve("A", "電車呢？")
    assert electric and electric.inherited_topic and electric.topic == "TRUNK_SPACE"
    assert electric.slots["powertrain"] == BEV
    recommend = manager.resolve("A", "那哪台比較適合？")
    assert recommend and recommend.goal == "RECOMMEND" and recommend.topic == "TRUNK_SPACE"


def test_entity_carryover_and_user_scopes_are_isolated() -> None:
    manager = ConversationContextManager()
    manager.update("A", topic="VEHICLE_COMPARISON", vehicle_ids=["bz4x", "rav4-hev"])
    manager.update("B", topic="VEHICLE_COMPARISON", vehicle_ids=["altis"])
    assert manager.resolve("A", "那空間呢？").inherited_entities is True
    assert manager.get("A").mentioned_vehicle_ids == ["bz4x", "rav4-hev"]
    assert manager.get("B").mentioned_vehicle_ids == ["altis"]


def test_explicit_battery_replaces_expired_or_inherited_trunk_topic() -> None:
    manager = ConversationContextManager()
    context = manager.update("A", topic="TRUNK_SPACE")
    context.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert manager.resolve("A", "電池可以用多久？") is None
    manager.update("A", topic="TRUNK_SPACE")
    result = manager.resolve("A", "先不管後車廂，電池安全呢？")
    assert result and result.topic == "BATTERY" and result.resolved_using_context is False


def test_cold_start_hydrates_database_row_and_expired_row_is_not_reused() -> None:
    first = ConversationContextManager()
    context = first.update("group-user", topic="TRUNK_SPACE", goal="RECOMMEND", slots={"cargo_space": "large"})
    row = {"context_json": context.payload(), "updated_at": context.updated_at.isoformat(), "expires_at": context.expires_at.isoformat()}
    # A separate manager represents another Vercel instance after a cold start.
    second = ConversationContextManager()
    loaded, source = second.hydrate("group-user", row)
    assert source == "DATABASE" and loaded.active_topic == "TRUNK_SPACE"
    resolved = second.resolve("group-user", "電車呢？")
    assert resolved and resolved.topic == "TRUNK_SPACE" and resolved.slots["powertrain"] == BEV
    expired = {**row, "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
    empty, source = ConversationContextManager().hydrate("expired", expired)
    assert source == "EMPTY" and empty.active_topic is None


def test_entity_replacement_does_not_accumulate_old_comparison_models() -> None:
    manager = ConversationContextManager()
    manager.update("A", vehicle_ids=["bz4x", "rav4"], goal="COMPARE")
    manager.update("A", vehicle_ids=["corolla-cross"], entity_operation="REPLACE")
    context = manager.get("A")
    assert context and context.mentioned_vehicle_ids == ["corolla-cross"]
    assert context.active_vehicle_id == "corolla-cross"
