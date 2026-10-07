"""Compatibility CLI: ``python -m tests.conversation_runner``."""

from tests.conversations.conversation_runner import main


if __name__ == "__main__":
    raise SystemExit(main())
