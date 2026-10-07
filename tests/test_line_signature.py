import base64
import hashlib
import hmac

from app.services.line_client import group_welcome_message
from app.services.line_signature import verify_line_signature


def test_valid_signature_is_accepted() -> None:
    secret = "test-secret"
    body = b'{"events":[]}'
    signature = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    assert verify_line_signature(body=body, signature=signature, channel_secret=secret)


def test_invalid_signature_is_rejected() -> None:
    assert not verify_line_signature(
        body=b'{"events":[]}', signature="not-a-signature", channel_secret="test-secret"
    )


def test_group_welcome_is_text_only_and_the_persistent_menu_is_flex() -> None:
    message = group_welcome_message()

    assert message["type"] == "text"
    assert "quickReply" not in message
