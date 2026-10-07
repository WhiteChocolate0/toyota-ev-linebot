"""Pytest entry point; test cases remain data-driven in scenarios.py."""

from tests.test_conversation_regression import assert_conversation_regression_suite


def test_golden_conversations() -> None:
    assert_conversation_regression_suite()
