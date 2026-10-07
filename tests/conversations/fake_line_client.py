"""Public Fake LINE client API used by conversation and snapshot tests."""

from .harness import RecordingLineClient


class FakeLineClient(RecordingLineClient):
    """In-memory LINE transport; it never sends a network request."""

    @property
    def reply_messages(self) -> list[str]:
        return self.replies

    @property
    def push_messages(self) -> list[str]:
        return []

    @property
    def flex_messages(self) -> list[str]:
        return self.replies

    @property
    def postbacks(self) -> list[dict]:
        return []

    def last_reply(self) -> str | None:
        return self.replies[-1] if self.replies else None

    def all_messages(self) -> list[str]:
        return list(self.replies)
