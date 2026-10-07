"""Normalize charging descriptions to ratios before a cost calculation."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_UNCLEAR_REPLY = "沒問題，你可以大概選一個：\n① 家充為主\n② 家充／公共各半\n③ 公共充電為主"


@dataclass(frozen=True)
class ChargingParseResult:
    home_charge_ratio: float
    public_charge_ratio: float
    primary_charging_type: str
    reply: str


class ChargingParser:
    def __init__(self, api_key: str | None = None, model: str | None = None, post: Any | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self._model = model or settings.gemini_model
        self._post = post

    @property
    def is_enabled(self) -> bool:
        return bool(self._api_key)

    def parse(self, text: str) -> ChargingParseResult | None:
        return self._parse_by_rules(text) or self._parse_with_ai(text)

    @staticmethod
    def clarification_reply() -> str:
        return _UNCLEAR_REPLY

    @staticmethod
    def _result(home: float, public: float) -> ChargingParseResult:
        primary = "home" if home > public else "public" if public > home else "mixed"
        primary_label = {"home": "家充", "public": "公共充電", "mixed": "家充／公共各半"}[primary]
        return ChargingParseResult(home, public, primary, f"了解，我先以家充 {home:.0%}、公共充電 {public:.0%} 幫你估算，之後也可以再調整比例。")

    @classmethod
    def _parse_by_rules(cls, text: str) -> ChargingParseResult | None:
        normalized = text.replace("裏", "裡").replace(" ", "").lower()
        if any(word in normalized for word in ("看情況", "都有", "不一定", "隨便")):
            return None
        # A one-word answer means that charging location is exclusive.
        if normalized in {"家裡", "家充", "住家"}:
            return cls._result(1, 0)
        if normalized in {"公共", "公充", "公共充電", "外面", "充電站"}:
            return cls._result(0, 1)

        # Explicit Arabic percentage pairs, in either order.
        percentages = re.findall(r"(\d+(?:\.\d+)?)%[^，,。；;]*?(家裡|家充|住家|公共|公充|外面|充電站)", normalized)
        if len(percentages) >= 2:
            home = public = None
            for amount, place in percentages:
                ratio = float(amount) / 100
                if any(marker in place for marker in ("家", "住")):
                    home = ratio
                else:
                    public = ratio
            if home is not None and public is not None and abs(home + public - 1) < 0.011:
                return cls._result(home, public)

        # Chinese tenths, such as 八成家充、兩成公共.
        tenths = re.findall(r"([一二三四五六七八九十兩])成[^，,。；;]*?(家裡|家充|住家|公共|公充|外面|充電站)", normalized)
        if len(tenths) >= 2:
            digits = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            home = public = None
            for amount, place in tenths:
                if any(marker in place for marker in ("家", "住")):
                    home = digits[amount] / 10
                else:
                    public = digits[amount] / 10
            if home is not None and public is not None and abs(home + public - 1) < 0.011:
                return cls._result(home, public)

        if any(word in normalized for word in ("一半", "各半", "差不多", "五五波")) and ("家" in normalized and any(word in normalized for word in ("公共", "公充", "外面"))):
            return cls._result(0.5, 0.5)
        if any(word in normalized for word in ("只能公共", "家裡不能充", "都在外面", "全都公共")):
            return cls._result(0, 1)
        if any(word in normalized for word in ("全部家", "幾乎都在家", "都在家", "只在家", "家裡")) and not any(word in normalized for word in ("公共", "公充", "外面")):
            return cls._result(0.95, 0.05)
        if any(word in normalized for word in ("幾乎都公共", "全部公共", "只用公共", "外面充")) and "家" not in normalized:
            return cls._result(0.05, 0.95)
        home_words = ("主要在家", "大多", "大部分", "平常在家", "家裡為主", "家充為主", "偶爾公共", "出遠門")
        public_words = ("公共為主", "大多公共", "大部分公共", "主要公共", "偶爾家充")
        if any(word in normalized for word in home_words) and "家" in normalized:
            return cls._result(0.75 if "家裡為主" in normalized or "家充為主" in normalized else 0.8, 0.25 if "家裡為主" in normalized or "家充為主" in normalized else 0.2)
        if any(word in normalized for word in public_words):
            return cls._result(0.2, 0.8)
        return None

    def _parse_with_ai(self, text: str) -> ChargingParseResult | None:
        if not self._api_key:
            return None
        payload = {
            "contents": [{"parts": [{"text": self._prompt(text)}]}],
            "generationConfig": {"thinkingConfig": {"thinkingLevel": "minimal"}, "maxOutputTokens": 128,
                "responseMimeType": "application/json", "responseSchema": {"type": "OBJECT", "properties": {
                    "status": {"type": "STRING"}, "home_charge_ratio": {"type": "NUMBER", "nullable": True},
                    "public_charge_ratio": {"type": "NUMBER", "nullable": True},
                }, "required": ["status", "home_charge_ratio", "public_charge_ratio"]}},
        }
        try:
            post = self._post or httpx.post
            response = post(_URL.format(model=self._model), headers={"x-goog-api-key": self._api_key}, json=payload, timeout=10)
            response.raise_for_status()
            raw = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
            home, public = raw["home_charge_ratio"], raw["public_charge_ratio"]
            if raw["status"] == "success" and isinstance(home, (int, float)) and isinstance(public, (int, float)) and 0 <= home <= 1 and 0 <= public <= 1 and abs(home + public - 1) < 0.011:
                return self._result(float(home), float(public))
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Charging parser AI fallback failed")
        return None

    @staticmethod
    def _prompt(text: str) -> str:
        return f"""你是充電方式解析器。判斷使用者的家充與公共充電比例。若語意不足以量化，status 回 need_clarification，兩個比例回 null。若可判定，status 回 success，比例必須相加為 1。主要在家且偶爾公共預設 0.8/0.2；家裡為主 0.75/0.25；各半 0.5/0.5；公共為主 0.2/0.8。只回 JSON。使用者：<message>{text}</message>"""


charging_parser = ChargingParser()
