import base64
import hashlib
import hmac


def verify_line_signature(*, body: bytes, signature: str | None, channel_secret: str) -> bool:
    """Verify LINE's HMAC-SHA256 signature against the unmodified request body."""
    if not signature or not channel_secret:
        return False

    digest = hmac.new(
        channel_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(signature, expected)
