import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_LOADING_URL = "https://api.line.me/v2/bot/chat/loading/start"


def group_welcome_message() -> dict:
    return {
        "type": "text",
        "text": (
            "大家好，我是「電車解惑所」⚡\n\n"
            "如果大家對電動車、TOYOTA、bZ4X、充電、續航、電池、成本或選車有問題，都可以直接問我。\n\n"
            "不知道從哪裡開始也沒關係，可以從下面選一個："
        ),
    }


class LineClient:
    """Small wrapper around LINE Messaging API used by the event router."""

    def _reply(self, reply_token: str, messages: list[dict]) -> None:
        access_token = get_settings().line_channel_access_token
        if not access_token:
            logger.error("LINE access token is not configured; reply was skipped")
            return

        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.post(
                    LINE_REPLY_URL,
                    json={"replyToken": reply_token, "messages": messages},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # LINE returns a useful validation body for malformed Flex payloads.
            logger.error("Unable to send LINE reply: %s", exc.response.text)
        except httpx.HTTPError:
            logger.exception("Unable to send LINE reply")

    def show_loading_animation(self, user_id: str, seconds: int = 5) -> None:
        """Show LINE's native waiting animation for a one-to-one AI rewrite.

        This endpoint does not support groups; a failure here must never block
        the eventual reply.
        """
        access_token = get_settings().line_channel_access_token
        if not access_token or not user_id:
            return
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.post(
                    LINE_LOADING_URL,
                    json={"chatId": user_id, "loadingSeconds": seconds},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Unable to display LINE loading animation")

    def reply_group_welcome(self, reply_token: str) -> None:
        from app.services.service_menu_flex import build_service_menu_flex
        self._reply(reply_token, [group_welcome_message(), build_service_menu_flex()])

    def reply_text(self, reply_token: str, text: str) -> None:
        self._reply(reply_token, [{"type": "text", "text": text}])

    def reply_text_with_quick_replies(self, reply_token: str, text: str, items: list[dict]) -> None:
        """Reply with LINE postback choices; callers provide already bounded items."""
        self._reply(reply_token, [{"type": "text", "text": text, "quickReply": {"items": items}}])

    def reply_flex(self, reply_token: str, flex_message: dict) -> None:
        self._reply(reply_token, [flex_message])

    def reply_text_and_flex(self, reply_token: str, text: str, flex_message: dict) -> None:
        """Use one reply-token request so first-use onboarding follows its answer."""
        self._reply(reply_token, [{"type": "text", "text": text}, flex_message])

    def reply_texts(self, reply_token: str, texts: list[str]) -> None:
        self._reply(reply_token, [{"type": "text", "text": text} for text in texts])
