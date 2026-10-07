"""Compatibility import; run ``pytest tests/conversations`` for this suite."""

from tests.conversations.test_conversations import test_golden_conversations as run_golden_conversations

__all__ = ["run_golden_conversations"]
