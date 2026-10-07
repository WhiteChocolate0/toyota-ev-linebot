"""A plain-language, owner-bound EV lifestyle suitability check."""
from dataclasses import dataclass, field
import re

from app.config import get_settings
from app.services.charging_feasibility import evaluate


@dataclass
class EvFitState:
    stage: str = "daily_km"
    values: dict[str, str] = field(default_factory=dict)


class EvFitManager:
    title = "我適合開電動車嗎？"
    prompts = {
        "daily_km": "你平常每天大約開多少公里？",
        "long_trip": "你多常需要開長途或跨縣市？",
        "long_charge_acceptance": "如果跑長途，中途安排一次充電你可以接受嗎？",
        "parking": "家裡有固定車位嗎？",
        "home_charge": "固定車位目前有哪些充電條件？可複選，選完請按「完成」。",
        "work_charge": "工作地點有可以使用的充電設備嗎？",
    }
    choices = {
        "daily_km": (("20 km 以下", "under_20"), ("20–40 km", "20_40"), ("40–60 km", "40_60"), ("60–100 km", "60_100"), ("100 km 以上", "over_100"), ("不確定", "unknown")),
        "long_trip": (("很少", "rare"), ("每月 1–2 次", "monthly"), ("每週都有", "weekly"), ("不確定", "unknown")),
        "long_charge_acceptance": (("可以接受", "accept"), ("有點麻煩", "inconvenient"), ("不太能接受", "unacceptable"), ("不確定", "unknown")),
        "parking": (("有", "yes"), ("沒有", "no"), ("不確定", "unknown")),
        "home_charge": (
            ("☐ 可安裝 220V 充電設備", "HOME_220V"),
            ("☐ 有一般 110V 插座", "HOME_110V"),
            ("☐ 需要再確認", "NEED_CONFIRMATION"),
            ("☐ 目前無法充電", "UNAVAILABLE"),
            ("完成", "HOME_CHARGE_DONE"),
        ),
        "work_charge": (("有", "yes"), ("沒有", "no"), ("不確定", "unknown"), ("不適用", "na")),
    }
    order = ("daily_km", "long_trip", "long_charge_acceptance", "parking", "home_charge", "work_charge")

    def __init__(self, home_110v_good_max_daily_km: int | None = None, home_110v_warning_max_daily_km: int | None = None) -> None:
        self._states: dict[str, EvFitState] = {}
        settings = get_settings()
        self._home_110v_good_max_daily_km = home_110v_good_max_daily_km or settings.ev_home_110v_good_max_daily_km
        self._home_110v_warning_max_daily_km = home_110v_warning_max_daily_km or settings.ev_home_110v_warning_max_daily_km

    def start(self, scope_id: str) -> str:
        self._states[scope_id] = EvFitState()
        return f"想知道你的生活適不適合 EV 嗎？\n回答幾個簡單問題，我會幫你找出目前最需要確認的地方。\n\n{self.prompts['daily_km']}"

    def is_active(self, scope_id: str) -> bool:
        return scope_id in self._states and self._states[scope_id].stage != "result"

    def quick_reply_items(self, scope_id: str) -> list[dict]:
        state = self._states.get(scope_id)
        if not state or state.stage not in self.choices:
            return []
        items = [{"type": "action", "action": {"type": "postback", "label": label, "data": f"fit={value}", "displayText": label}}
                for label, value in self.choices[state.stage]]
        items.append({"type": "action", "action": {"type": "postback", "label": "結束評估", "data": "action=cancel_flow&flow_id=EV_FIT", "displayText": "結束評估"}})
        return items

    @staticmethod
    def parse_natural_answer(stage: str, message: str) -> str | None:
        compact = message.strip().casefold().replace(" ", "")
        if stage == "daily_km":
            found = re.search(r"(\d{1,3})\s*(?:公里|km)?", compact)
            if found:
                km = int(found.group(1)); return "under_20" if km < 20 else "20_40" if km <= 40 else "40_60" if km <= 60 else "60_100" if km <= 100 else "over_100"
        if stage == "long_trip":
            if any(word in compact for word in ("很少", "幾乎不", "不常")): return "rare"
            if any(word in compact for word in ("每月", "偶爾", "一兩次")): return "monthly"
            if any(word in compact for word in ("每週", "常常", "都有")): return "weekly"
        if stage == "long_charge_acceptance":
            if any(word in compact for word in ("可以", "沒問題", "接受")): return "accept"
            if any(word in compact for word in ("有點麻煩", "麻煩")): return "inconvenient"
            if any(word in compact for word in ("不太想", "不能接受", "不接受")): return "unacceptable"
        if stage == "parking":
            if any(word in compact for word in ("沒有固定車位", "沒車位")): return "no"
            if any(word in compact for word in ("有車位", "固定車位", "租車位")): return "yes"
        if stage == "home_charge":
            if any(word in compact for word in ("220", "可以裝")): return "HOME_220V"
            if "110" in compact: return "HOME_110V"
            if any(word in compact for word in ("管委會", "不確定", "要問")): return "NEED_CONFIRMATION"
            if any(word in compact for word in ("不能裝", "無法充")): return "UNAVAILABLE"
        if stage == "work_charge":
            if any(word in compact for word in ("公司可以", "公司有", "可以充")): return "yes"
            if any(word in compact for word in ("公司沒有", "不能充")): return "no"
        return None

    def advance(self, scope_id: str, value: str, home_110v_feature: str | None = None) -> str:
        state = self._states.get(scope_id)
        if not state:
            return self.start(scope_id)
        allowed_values = {item_value for _, item_value in self.choices.get(state.stage, ())}
        # Postback payloads are already canonical values.  Parsing them as
        # natural language makes ``over_100`` look like the number 100 and
        # incorrectly changes it to the 60–100 km bucket.
        if value not in allowed_values:
            value = self.parse_natural_answer(state.stage, value) or value
        if value not in allowed_values:
            return self.prompts[state.stage]
        if state.stage == "home_charge":
            selected = set(filter(None, state.values.get("home_charge_sources", "").split(",")))
            if value == "HOME_CHARGE_DONE":
                if not selected:
                    return "請至少選一項；若目前不確定，可選「需要再確認」。"
                # Assessment keeps the complete set while legacy consumers use
                # a deterministic best available home source.
                state.values["home_charge_sources"] = ",".join(sorted(selected))
                state.values["home_charge"] = "HOME_220V" if "HOME_220V" in selected else "HOME_110V" if "HOME_110V" in selected else "NEED_CONFIRMATION" if "NEED_CONFIRMATION" in selected else "UNAVAILABLE"
                state.stage = "work_charge"
                return self.prompts[state.stage]
            selected.symmetric_difference_update({value})
            state.values["home_charge_sources"] = ",".join(sorted(selected))
            labels = {"HOME_220V": "可安裝 220V", "HOME_110V": "有 110V", "NEED_CONFIRMATION": "待確認", "UNAVAILABLE": "目前無法充電"}
            current = "、".join(labels[item] for item in sorted(selected)) or "尚未選擇"
            return f"目前已選：{current}\n可繼續複選，完成後請按「完成」。"
        state.values[state.stage] = value
        if state.stage == "parking" and value != "yes":
            state.values["home_charge"] = "UNAVAILABLE" if value == "no" else "NEED_CONFIRMATION"
            state.stage = "work_charge"
            return self.prompts[state.stage]
        index = self.order.index(state.stage)
        if index == len(self.order) - 1:
            state.stage = "result"
            return self.result_text(scope_id, home_110v_feature=home_110v_feature)
        state.stage = self.order[index + 1]
        return self.prompts[state.stage]

    def result_text(self, scope_id: str, home_110v_feature: str | None = None) -> str:
        values = self._states[scope_id].values
        daily_status, daily_text = self._daily_dimension(values.get("daily_km", "unknown"))
        home_status, home_text = self._home_dimension(values)
        long_status, long_text = self._long_dimension(values)
        work_status, work_text = self._work_dimension(values.get("work_charge", "unknown"))
        charging = evaluate(values, self._daily_km_estimate(values.get("daily_km", "unknown")), self._home_110v_good_max_daily_km, self._home_110v_warning_max_daily_km)
        blocker, next_step = self._blocker(daily_status, home_status, long_status, values)
        summary = self._summary(home_status, long_status, daily_status)
        feature_hint = ""
        if values.get("parking") == "yes" and values.get("home_charge") == "HOME_110V" and home_110v_feature:
            feature_hint = (
                f"\n\n💡 bZ4X 補電彈性\n{home_110v_feature}；"
                "若每日里程較高，220V 充電設備會更適合。"
            )
        return (
            f"{self.title}\n\n{summary}\n\n"
            f"{self._symbol(daily_status)} 日常里程：{daily_text}\n"
            f"{self._symbol(home_status)} 家庭補電：{home_text}\n"
            f"{self._symbol(long_status)} 長途需求：{long_text}\n"
            f"{self._symbol(work_status)} 工作地補電：{work_text}\n\n"
            f"【你的補電方式】\n主要：{charging.primary_source or '尚未找到可靠補電方式'}\n備用：{charging.backup_source or '尚未確認'}\n長途：{charging.long_trip_fit}\n\n"
            f"最需要確認：{blocker}\n\n下一步：{next_step}{feature_hint}\n\n"
            "※ 本結果僅依目前生活條件整理，不構成購車建議。"
        )

    @staticmethod
    def _symbol(status: str) -> str:
        return {"good": "✅", "warning": "🟡", "attention": "❗", "neutral": "◻️"}[status]

    @staticmethod
    def _daily_dimension(value: str) -> tuple[str, str]:
        if value in {"under_20", "20_40", "40_60", "60_100"}: return "good", "適合"
        if value == "over_100": return "warning", "里程較高，需安排補電"
        return "warning", "待確認"

    def _home_dimension(self, values: dict[str, str]) -> tuple[str, str]:
        home_status = values.get("home_charge")
        if values.get("parking") == "yes" and home_status == "HOME_220V":
            return "good", "220V 充電設備可用"
        if values.get("parking") == "yes" and home_status == "HOME_110V":
            mileage = self._daily_km_estimate(values.get("daily_km", "unknown"))
            if mileage is not None and mileage <= self._home_110v_good_max_daily_km:
                return "good", "110V 可作日常補電"
            if mileage is not None and mileage <= self._home_110v_warning_max_daily_km:
                return "warning", "110V 可補電，建議確認 220V"
            if mileage is not None:
                return "attention", "110V 不適合作為主要補電"
            return "warning", "110V 可補電，需確認日常里程"
        if values.get("parking") == "no": return "attention", "沒有固定車位"
        if home_status == "NEED_CONFIRMATION": return "warning", "待確認"
        return "attention", "目前不方便"

    @staticmethod
    def _daily_km_estimate(value: str) -> int | None:
        # The 60–100 km answer spans the 80 km policy boundary; use its
        # midpoint so it remains a caution, while 100+ becomes attention.
        return {"under_20": 20, "20_40": 40, "40_60": 60, "60_100": 80, "over_100": 100}.get(value)

    @staticmethod
    def _long_dimension(values: dict[str, str]) -> tuple[str, str]:
        trips, acceptance = values.get("long_trip"), values.get("long_charge_acceptance")
        if trips == "rare" or acceptance == "accept": return "good", "可規劃"
        if trips == "weekly" and acceptance == "unacceptable": return "attention", "需仔細評估"
        return "warning", "需確認充電接受度"

    @staticmethod
    def _work_dimension(value: str) -> tuple[str, str]:
        if value == "yes": return "good", "方便"
        if value in {"no", "na"}: return "neutral", "不列入日常假設"
        return "warning", "待確認"

    @staticmethod
    def _summary(home: str, long_trip: str, daily: str) -> str:
        if home == "attention": return "目前最大的限制不是里程，而是固定充電條件。"
        if home == "warning": return "你的日常用車條件大致適合 EV，但家用充電條件還需要先確認。"
        if long_trip == "attention": return "你的日常用車條件大致適合 EV，但長途充電接受度需要先確認。"
        if daily == "warning": return "你的日常用車條件大致適合 EV，但高里程下的補電安排需要先確認。"
        return "整體來看，你的日常用車條件蠻適合 EV。"

    @staticmethod
    def _blocker(daily: str, home: str, long_trip: str, values: dict[str, str]) -> tuple[str, str]:
        if values.get("home_charge") == "HOME_110V" and home in {"warning", "attention"}:
            return "家中是否能進一步安裝 220V 充電設備", "確認固定車位的供電與社區安裝條件，再比較長期用車成本。"
        if home == "attention": return "固定充電條件", "先確認常用公共充電站的距離、等候與夜間充電安排，再比較長期用車成本。"
        if home == "warning": return "家中充電條件", "向社區管理單位或停車場確認是否可安裝充電設備。"
        if long_trip == "attention": return "長途充電接受度", "先試著規劃一次常用跨縣市路線的中途充電。"
        if daily == "warning": return "每日高里程下的補電安排", "確認家充或工作地補電能否支援你的日常里程。"
        return "實際長期用車成本", "確認充電條件後，可以再比較 EV 與油車的長期使用成本。"


ev_fit_manager = EvFitManager()
