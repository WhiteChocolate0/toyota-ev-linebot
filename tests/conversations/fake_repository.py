"""In-memory repository fixture with the EventProcessor-facing contract."""

from .harness import ScenarioRepository


class FakeRepository(ScenarioRepository):
    """Alias with an intentionally production-shaped name for test authors."""
