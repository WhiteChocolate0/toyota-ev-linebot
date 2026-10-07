"""Minimal, structured context for a vehicle-comparison follow-up."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ComparisonContext:
    model_names: tuple[str, ...]
    current_drivetrain: str | None
    expires_at: datetime


class ComparisonContextManager:
    """Keeps only intent and model names, never raw family-chat messages."""

    _ttl = timedelta(minutes=15)
    _yes = ("好", "好呀", "好的", "可以", "可以啊", "要", "開始", "幫我算", "比較看看")
    _no = ("不用", "不要", "先不用", "晚點", "沒關係")

    def __init__(self) -> None:
        self._states: dict[str, ComparisonContext] = {}

    def offer(self, scope_id: str, profiles: list[dict]) -> None:
        model_names = tuple(dict.fromkeys(profile["model_name"] for profile in profiles))
        if not model_names:
            return
        current_profile = next((profile for profile in profiles if profile["model_name"].lower() != "bz4x"), profiles[0])
        self._states[scope_id] = ComparisonContext(
            model_names=model_names,
            current_drivetrain=current_profile.get("drivetrain"),
            expires_at=datetime.now(UTC) + self._ttl,
        )

    def respond(self, scope_id: str, text: str) -> tuple[str, ComparisonContext | None] | None:
        context = self._states.get(scope_id)
        if not context:
            return None
        if context.expires_at <= datetime.now(UTC):
            self._states.pop(scope_id, None)
            return None
        normalized = text.strip().lower().replace("！", "").replace("。", "")
        if normalized in self._yes:
            self._states.pop(scope_id, None)
            return "accepted", context
        if normalized in self._no:
            self._states.pop(scope_id, None)
            return "declined", context
        return None

    def clear(self, scope_id: str) -> None:
        self._states.pop(scope_id, None)


comparison_context_manager = ComparisonContextManager()
