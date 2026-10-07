"""Data-driven, per-user energy-cost comparison flow."""
import time
import uuid
from dataclasses import dataclass, field
import re

from app.services.charging_parser import ChargingParser, charging_parser
from app.services.fuel_price_service import FuelPriceService, fuel_price_service
from app.services.powertrain import BEV, HEV, ICE_DIESEL, ICE_GASOLINE, PHEV, POWERTRAIN_LABELS, normalize_powertrain
from app.services.tco_calculator import LoanTerms, TcoCalculator, TcoInputs, VehicleTcoProfile
from app.services.cost_sensitivity import apply_scenario, difference

# FULL_TCO always preserves this order. A component's state is separate from
# its numeric amount so `0`, missing input and not-applicable never collapse.
FULL_TCO_CATEGORIES = (
    ("車價 / 折舊", "purchase_price"), ("能源", "energy"), ("保養", "maintenance"),
    ("保險", "insurance"), ("稅費", "tax"), ("輪胎", "tires"), ("停車", "parking"),
    ("貸款利息", "loan_interest"), ("貸款手續費", "loan_fee"),
    ("充電設備", "charger_installation"), ("其他", "miscellaneous"), ("殘值扣抵", "residual_value_credit"),
)


def format_full_tco_component(value: float | int | None, status: str = "calculated") -> str:
    """Presentation rule shared by text and Flex full-TCO views."""
    if status == "not_applicable":
        return "不適用"
    if value is None or status == "missing_input":
        return "尚未納入"
    return f"NT$ {value:,.0f}"


def derive_required_inputs(vehicle_a: dict, vehicle_b: dict) -> list[str]:
    """Plan only unknown, powertrain-relevant inputs for this vehicle pair."""
    fields = ["monthly_km", "ownership_years"]
    for target, vehicle in (("vehicle_a", vehicle_a), ("vehicle_b", vehicle_b)):
        powertrain = vehicle.get("powertrain")
        if powertrain in {ICE_GASOLINE, ICE_DIESEL, HEV, PHEV} and not vehicle.get("fuel_efficiency_km_per_l"):
            fields.append(f"{target}_fuel_efficiency")
        if powertrain in {BEV, PHEV} and not vehicle.get("electric_efficiency_km_per_kwh"):
            fields.append(f"{target}_electric_efficiency")
    powertrains = {vehicle_a.get("powertrain"), vehicle_b.get("powertrain")}
    if powertrains & {ICE_GASOLINE, ICE_DIESEL, HEV, PHEV}:
        fields.append("fuel_price")
    if powertrains & {BEV, PHEV}:
        fields += ["charging_ratio", "home_electricity_price", "public_charging_price"]
    if PHEV in powertrains:
        fields.append("phev_electric_share")
    return fields


@dataclass
class CostFlowState:
    stage: str = "vehicle_type"
    values: dict[str, object] = field(default_factory=dict)


class CostFlowManager:
    default_ownership_years = 8
    flow_timeout_seconds = 15 * 60
    _models_by_powertrain = {
        ICE_GASOLINE: ("YARiS CROSS", "TOWN ACE 廂型", "TOWN ACE 貨卡", "VIOS", "ALTIS", "ALTIS GR SPORT", "COROLLA CROSS", "COROLLA CROSS GR SPORT", "COROLLA SPORT", "CAMRY", "GR86", "GR YARIS"),
        ICE_DIESEL: ("HILUX", "LAND CRUISER"),
        HEV: ("CROWN CROSSOVER", "RAV4", "RAV4 ADVENTURE", "RAV4 GR SPORT", "ALTIS", "ALTIS GR SPORT", "COROLLA CROSS", "COROLLA CROSS GR SPORT", "CAMRY", "SIENNA", "ALPHARD"),
        PHEV: ("CROWN SPORT", "RAV4 PHEV", "PRIUS PHEV", "ALPHARD PHEV"), BEV: ("URBAN CRUISER", "bZ4X"),
    }
    _prompts = {
        "vehicle_type": "我們先選第一台想比較的 TOYOTA 車款。\n它是哪種動力？\n汽油車、柴油車、油電車、PHEV、BEV\n\n想停止可輸入「取消試算」。",
        "vehicle_b_type": "接著想跟哪種動力比較？\n汽油車、柴油車、油電車、PHEV、BEV",
        "monthly_km": "接著請告訴我你的用車頻率與里程。可輸入「每天 20 公里」或「上下班單程 15 公里」。",
        "calculation_mode": "想怎麼算？\n⚡ 快速試算會使用官方規格與系統預設；⚙️ 精準試算可調整能源與充電條件。",
        "ownership_years": "預計這台車會持有多久？可選 3、5、8、10 年；其他年限可直接輸入 1～15 年。",
        "phev_preset": "🔌 你的 PHEV 使用方式比較接近哪一種？",
        "charging_ratio": "你平常是家充為主、公共為主，還是大約各半？",
        "home_electricity_price": "如果你知道實際平均家充電價，可以直接輸入；不確定的話回覆「使用預設」。",
        "public_charging_price": "如果你知道常用公共充電的平均電價，可以直接輸入；不確定的話回覆「使用預設」。",
        "phev_electric_share": "PHEV 平常約有幾成里程用純電行駛？例如 60 代表 60%。",
        "full_cost_residual": "完整成本是否要估算期末殘值？不確定時可選「暫不估算」，避免把推測當成事實。",
        "full_cost_a_residual": "請輸入第一台預估殘值率（0～100，例如 45）。這是你的情境假設，非官方保證。",
        "full_cost_b_residual": "請輸入第二台預估殘值率（0～100，例如 45）。這是你的情境假設，非官方保證。",
        "full_cost_a_purchase_price": "請輸入第一台車的成交／預計車價（元）。",
        "full_cost_b_purchase_price": "請輸入第二台車的成交／預計車價（元）。",
        "full_cost_fuel_price": "目前沒有可用的油價資料；請輸入本次試算油價（元／L）。",
        "full_cost_a_maintenance": "請輸入第一台每年保養預算（元）；不納入可輸入 0。",
        "full_cost_b_maintenance": "請輸入第二台每年保養預算（元）；不納入可輸入 0。",
        "full_cost_a_insurance": "請輸入第一台每年保險預算（元）；不納入可輸入 0。",
        "full_cost_b_insurance": "請輸入第二台每年保險預算（元）；不納入可輸入 0。",
        "full_cost_a_tax": "請輸入第一台每年牌照／燃料等稅費預算（元）；不納入可輸入 0。",
        "full_cost_b_tax": "請輸入第二台每年牌照／燃料等稅費預算（元）；不納入可輸入 0。",
        "full_cost_a_tire_set": "請輸入第一台一組輪胎預算（元）；不納入可輸入 0。",
        "full_cost_a_tire_life": "第一台輪胎預計每幾公里更換一組？不納入可輸入 0。",
        "full_cost_b_tire_set": "請輸入第二台一組輪胎預算（元）；不納入可輸入 0。",
        "full_cost_b_tire_life": "第二台輪胎預計每幾公里更換一組？不納入可輸入 0。",
        "full_cost_parking": "請輸入每年停車預算（兩車共用條件；元）；不納入可輸入 0。",
        "full_cost_miscellaneous": "請輸入每年其他用車雜支預算（元）；不納入可輸入 0。",
        "full_cost_charger": "請輸入家用充電設備一次性安裝預算（元）；不納入可輸入 0。",
        "full_cost_loan_choice": "兩台車都使用相同貸款條件估算嗎？若選「是」，接著會詢問頭期款、利率、年限與手續費。",
        "full_cost_loan_down_payment": "請輸入預計頭期款（元；此條件會套用於兩台車）。",
        "full_cost_loan_rate": "請輸入貸款年利率（百分比，例如 2.5）。",
        "full_cost_loan_years": "請輸入貸款年限（1～15 年）。",
        "full_cost_loan_fee": "請輸入貸款手續費（元）；沒有可輸入 0。",
    }

    def __init__(self, fuel_prices: FuelPriceService | None = None, charging: ChargingParser | None = None) -> None:
        self._states: dict[str, CostFlowState] = {}; self._followups: dict[str, str] = {}
        self._fuel_prices = fuel_prices or fuel_price_service; self._charging = charging or charging_parser

    def start(self, scope_id: str, *, group_id: str = "", owner_user_id: str = "") -> str:
        self._states[scope_id] = CostFlowState(values={
            "ownership_years": self.default_ownership_years,
            "group_id": group_id,
            "flow_owner_user_id": owner_user_id,
            "pending_expected_user_id": owner_user_id,
            "flow_status": "active",
            "last_activity_at": time.time(),
        }); self._followups.pop(scope_id, None)
        return self._prompts["vehicle_type"]

    def group_flow_owner(self, group_id: str) -> str | None:
        """Return an owner only for an unfinished group wizard."""
        for state in self._states.values():
            if state.values.get("group_id") == group_id and state.values.get("flow_status") == "active":
                owner = state.values.get("flow_owner_user_id")
                if isinstance(owner, str) and owner:
                    return owner
        return None

    def cancel(self, scope_id: str) -> str | None:
        self._followups.pop(scope_id, None)
        return "已取消成本試算；想重新開始時，輸入「成本試算」即可。" if self._states.pop(scope_id, None) else None

    def is_active(self, scope_id: str) -> bool:
        state = self._states.get(scope_id)
        return bool(state and state.values.get("flow_status", "active") == "active")

    def pause_if_expired(self, scope_id: str, now: float | None = None) -> bool:
        state = self._states.get(scope_id)
        if not state or state.values.get("flow_status") != "active":
            return False
        if (now or time.time()) - float(state.values.get("last_activity_at", 0)) < self.flow_timeout_seconds:
            return False
        state.values["flow_status"] = "paused"
        return True

    def is_paused(self, scope_id: str) -> bool:
        return bool(self._states.get(scope_id) and self._states[scope_id].values.get("flow_status") == "paused")

    def resume(self, scope_id: str) -> str | None:
        state = self._states.get(scope_id)
        if not state or state.values.get("flow_status") != "paused":
            return None
        state.values.update(flow_status="active", last_activity_at=time.time())
        return self._prompt_for(state)

    def touch(self, scope_id: str) -> None:
        state = self._states.get(scope_id)
        if state and state.values.get("flow_status") == "active":
            state.values["last_activity_at"] = time.time()
    def current_stage(self, scope_id: str) -> str: return self._states[scope_id].stage
    def current_prompt(self, scope_id: str) -> str: return self._prompt_for(self._states[scope_id])
    def expects_monthly_mileage(self, scope_id: str) -> bool: return self._states.get(scope_id, CostFlowState()).stage == "monthly_km"
    def expects_vehicle_model(self, scope_id: str) -> bool: return self._states.get(scope_id, CostFlowState()).stage in {"vehicle_model", "vehicle_b_model"}
    def pop_followup(self, scope_id: str) -> str | None: return self._followups.pop(scope_id, None)
    def calculation_id(self, scope_id: str) -> str: return str(self._states[scope_id].values.get("calculation_id", ""))

    def sensitivity(self, scope_id: str, scenario_type: str) -> tuple[str, dict[str, object]] | None:
        state = self._states.get(scope_id)
        if not state or scenario_type not in {"LOW_MILEAGE", "HIGH_MILEAGE", "SHORT_OWNERSHIP", "LONG_OWNERSHIP", "HOME_CHARGING_HEAVY", "PUBLIC_CHARGING_HEAVY", "FUEL_PRICE_UP", "ELECTRICITY_PRICE_UP"}: return None
        base = dict(state.values); scenario, override = apply_scenario(base, scenario_type)
        base_result, scenario_result = self._calculate(base), self._calculate(scenario)
        label = {"HIGH_MILEAGE": "每月里程增加", "LOW_MILEAGE": "每月里程降低", "SHORT_OWNERSHIP": "持有較短", "LONG_OWNERSHIP": "持有較久", "HOME_CHARGING_HEAVY": "家充為主", "PUBLIC_CHARGING_HEAVY": "公共充電為主", "FUEL_PRICE_UP": "油價 +10%", "ELECTRICITY_PRICE_UP": "電價 +10%"}[scenario_type]
        text = f"【如果條件改變：{label}】\n\n原情境每年差額：NT$ {difference(base_result)}\n新情境每年差額：NT$ {difference(scenario_result)}\n\n這次差異由「{label}」這個情境假設造成；以下為情境分析，不代表未來油價、電價或殘值預測。"
        return text, {"parent_calculation_id": self.calculation_id(scope_id), "scenario_type": scenario_type, "override_json": override, "result_json": {"text": scenario_result}}

    def calculation_snapshot(self, scope_id: str) -> dict[str, object] | None:
        """Return the durable, non-sensitive inputs for the current result."""
        state = self._states.get(scope_id)
        if not state or not state.values.get("calculation_id"):
            return None
        a, b = state.values.get("vehicle_a"), state.values.get("vehicle_b")
        if not isinstance(a, dict) or not isinstance(b, dict):
            return None
        values = state.values
        return {
            "calculation_id": values["calculation_id"],
            "vehicle_a_id": a.get("id"),
            "vehicle_b_id": b.get("id"),
            "monthly_mileage": values.get("monthly_km"),
            "ownership_years": values.get("ownership_years"),
            "fuel_price": values.get("fuel_price"),
            "home_charge_ratio": values.get("home_charge_ratio"),
            "public_charge_ratio": values.get("public_charge_ratio"),
            "home_electricity_price": values.get("home_electricity_price"),
            "public_electricity_price": values.get("public_charging_price"),
            "phev_electric_ratio": values.get("phev_electric_share"),
            "assumptions": {"calculation_mode": values.get("calculation_mode", "quick"), "full_tco": values.get("full_cost_result", "")},
            "current_result": {"text": values.get("full_cost_result") or values.get("current_result", ""), "line_items": values.get("full_tco_line_items", {})},
        }

    def flow_snapshot(self, scope_id: str) -> dict[str, object] | None:
        state = self._states.get(scope_id)
        if not state:
            return None
        values = state.values
        return {"owner_user_id": values.get("flow_owner_user_id", ""), "current_state": state.stage,
                "pending_field": state.stage if values.get("flow_status") == "active" else None,
                "status": values.get("flow_status", "active")}

    def result_action(self, scope_id: str, action: str, params: dict[str, list[str]], source_type: str) -> tuple[str, list[dict]] | None:
        state = self._states.get(scope_id)
        if not state or params.get("calculation_id", [""])[0] != state.values.get("calculation_id"):
            return None
        a, b = state.values.get("vehicle_a"), state.values.get("vehicle_b")
        if not isinstance(a, dict) or not isinstance(b, dict): return None
        electrified = {BEV, PHEV} & {a["powertrain"], b["powertrain"]}
        fuelled = {ICE_GASOLINE, ICE_DIESEL, HEV, PHEV} & {a["powertrain"], b["powertrain"]}
        cid = state.values["calculation_id"]
        back = {"type": "action", "action": {"type": "postback", "label": "返回結果", "data": f"action=show_cost_result&calculation_id={cid}"}}
        if action == "edit_cost_inputs":
            state.stage = "edit_cost_menu"
            fields = [("每月里程", "mileage"), ("持有年限", "ownership_years")]
            if electrified: fields += [("充電比例", "charging_ratio"), ("家充電價", "home_electricity_price"), ("公共充電電價", "public_charging_price")]
            if fuelled: fields += [("油價", "fuel_price")]
            if PHEV in {a["powertrain"], b["powertrain"]}: fields += [("PHEV 使用比例", "phev_electric_ratio")]
            items = [{"type": "action", "action": {"type": "postback", "label": label, "data": f"action=edit_field&field={field}&calculation_id={cid}"}} for label, field in fields]
            items += [{"type": "action", "action": {"type": "postback", "label": "更換比較車款", "data": f"action=change_vehicle&calculation_id={cid}"}}, back]
            return "想調整哪一項？", items
        if action == "edit_field":
            field = params.get("field", [""])[0]
            prompts = {"mileage": "請輸入新的每月里程，例如 1200。", "ownership_years": "請輸入新的持有年限（1～15 年）。", "charging_ratio": "請選家充為主、各半或公共充電為主。", "home_electricity_price": "請輸入家充電價（元／度）。", "public_charging_price": "請輸入公共充電電價（元／度）。", "fuel_price": "請輸入油價（元／L）。", "phev_electric_ratio": "請輸入 PHEV 純電使用比例（0～100）。"}
            if field not in prompts: return None
            state.stage = "edit_value"; state.values["editing_field"] = field
            return prompts[field], [back]
        if action == "view_full_cost":
            state.stage = "full_cost_view"
            return "目前這次試算只有能源成本。\n\n如果要看完整持有成本，還需要補充：\n• 保險\n• 保養\n• 貸款\n• 停車\n• 殘值", [{"type": "action", "action": {"type": "postback", "label": "補充完整資料", "data": f"action=add_full_cost_data&calculation_id={cid}"}}, back]
        if action == "add_full_cost_data":
            state.stage = "full_cost_residual"
            return self._prompts[state.stage], self._full_cost_quick_replies(state)
        if action == "share_result":
            state.stage = "share_menu"
            if source_type == "group":
                labels = [("產生分享卡", "generate_share_card"), ("複製摘要", "copy_summary"), ("儲存試算結果", "save_calculation")]
                text = "這次試算已在家庭群組中，可產生分享卡、複製摘要或儲存結果。"
            else:
                labels = [("產生分享卡", "generate_share_card"), ("分享給家人", "share_to_family"), ("邀請我進家庭群組", "invite_to_group")]
                text = "可以把這次結果分享給家人。"
            return text, [{"type": "action", "action": {"type": "postback", "label": label, "data": f"action={act}&calculation_id={cid}"}} for label, act in labels] + [back]
        if action == "show_cost_result":
            state.stage = "cost_result"; return str(state.values.get("current_result", "目前沒有結果。")), []
        if action == "generate_share_card":
            return str(state.values.get("current_result", "目前沒有結果。")), [back]
        if action == "copy_summary":
            return self._share_summary(state.values), [back]
        if action == "save_calculation":
            return "已儲存這次試算結果；之後可從目前對話返回查看。", [back]
        if action == "share_to_family":
            return self._share_summary(state.values) + "\n\n可將這段摘要轉傳給家人。", [back]
        if action == "invite_to_group":
            return "請從 LINE 群組的邀請或加入功能將「電車解惑所」加入家庭群組；加入後可在群組中共同查看試算。", [back]
        return None

    def apply_edit(self, scope_id: str, value: str) -> str | None:
        state = self._states.get(scope_id)
        if not state or state.stage != "edit_value": return None
        field, cleaned = str(state.values.get("editing_field", "")), value.strip()
        number = self._number(cleaned)
        if field == "mileage":
            number = number if number is not None else self._daily_km(cleaned)
            if number is None: return "請輸入每月里程，例如 1200。"
            state.values["monthly_km"] = number
        elif field == "ownership_years":
            years = self._years(cleaned)
            if years is None or not 1 <= years <= 15: return "請輸入 1～15 年。"
            state.values["ownership_years"] = years
        elif field == "charging_ratio":
            parsed = self._charging.parse(cleaned)
            if not parsed: return self._charging.clarification_reply()
            state.values.update(home_charge_ratio=parsed.home_charge_ratio, public_charge_ratio=parsed.public_charge_ratio)
        elif field == "phev_electric_ratio":
            if number is None or not 0 <= number <= 100: return "請輸入 0～100。"
            state.values["phev_electric_share"] = number / 100
        elif field in {"home_electricity_price", "public_charging_price", "fuel_price"}:
            if number is None or number <= 0: return "請輸入大於 0 的數字。"
            state.values[field] = number
        else: return None
        state.stage = "cost_result"
        state.values["flow_status"] = "completed"
        state.values["pending_expected_user_id"] = None
        result = self._calculate(state.values)
        state.values["current_result"] = result
        return result

    @staticmethod
    def _share_summary(values: dict[str, object]) -> str:
        lines = str(values.get("current_result", "")).splitlines()
        safe = [line for line in lines if any(key in line for key in ("能源成本比較", "：約 NT$", "每年約差", "累積約差", "僅比較能源成本"))]
        return "\n".join(safe)

    def quick_reply_items(self, scope_id: str) -> list[dict]:
        """Selectable, postback-backed options for the current strict state."""
        state = self._states[scope_id]
        if state.stage in {"vehicle_type", "vehicle_b_type"}:
            return [
                {"type": "action", "action": {"type": "postback", "label": label, "data": f"powertrain={code}", "displayText": label}}
                for label, code in (("⛽ 汽油車", ICE_GASOLINE), ("🛻 柴油車", ICE_DIESEL), ("🌱 油電車 HEV", HEV), ("🔌 插電式油電 PHEV", PHEV), ("⚡ 純電車 BEV", BEV))
            ]
        if state.stage in {"vehicle_model", "vehicle_b_model"}:
            powertrain = str(state.values["pending_powertrain"])
            return [{"type": "action", "action": {"type": "postback", "label": model[:20], "data": f"model={model}", "displayText": model}} for model in self._models_by_powertrain[powertrain]][:13]
        if state.stage == "monthly_km":
            return [{"type": "action", "action": {"type": "postback", "label": label, "data": f"mileage={value}", "displayText": label}} for label, value in (("每月 300 km 以下", "300"), ("每月 300–800 km", "550"), ("每月 800–1500 km", "1150"), ("每月 1500–2500 km", "2000"), ("每月 2500 km 以上", "2800"), ("我想自己輸入", "custom"))]
        if state.stage == "calculation_mode":
            return [{"type": "action", "action": {"type": "postback", "label": label, "data": f"mode={value}", "displayText": label}} for label, value in (("⚡ 快速試算", "quick"), ("⚙️ 精準試算", "advanced"))]
        if state.stage == "ownership_years":
            return [{"type": "action", "action": {"type": "postback", "label": label, "data": f"years={value}", "displayText": label}} for label, value in (("3 年", "3"), ("5 年", "5"), ("8 年", "8"), ("10 年", "10"), ("使用建議值", "5"))]
        if state.stage == "phev_preset":
            return [{"type": "action", "action": {"type": "postback", "label": label, "data": f"phev_preset={value}", "displayText": label}} for label, value in (("A｜平常幾乎都充電", "0.8"), ("B｜充電與用油差不多", "0.5"), ("C｜很少充電，主要用油", "0.2"), ("D｜我要自己設定", "custom"))]
        return []

    @staticmethod
    def _full_cost_quick_replies(state: CostFlowState) -> list[dict]:
        if state.stage == "full_cost_residual":
            choices = (("暫不估算殘值", "exclude"), ("手動輸入殘值率", "manual"))
        elif state.stage == "full_cost_loan_choice":
            choices = (("不使用貸款", "no"), ("使用相同貸款條件", "yes"))
        else:
            return []
        return [{"type": "action", "action": {"type": "postback", "label": label, "data": f"full_cost={value}", "displayText": label}} for label, value in choices]

    def selected_vehicle(self, scope_id: str) -> tuple[str, str] | None:
        state = self._states.get(scope_id); target = state.values.get("last_vehicle_target") if state else None
        vehicle = state.values.get(f"vehicle_{target}") if state and target in {"a", "b"} else None
        return (str(vehicle["model_name"]), str(vehicle["powertrain"])) if isinstance(vehicle, dict) else None

    @staticmethod
    def _vehicle(model: str, powertrain: str, profile: dict | None = None) -> dict:
        profile = profile or {}
        return {"id": profile.get("id"), "model_name": profile.get("model_name", model), "trim_name": profile.get("trim_name"),
                "powertrain": normalize_powertrain(str(profile.get("drivetrain", powertrain))) or powertrain,
                "purchase_price_ntd": profile.get("purchase_price_ntd"), "fuel_efficiency_km_per_l": profile.get("fuel_efficiency_km_per_l"),
                "electric_efficiency_km_per_kwh": profile.get("electric_efficiency_km_per_kwh")}

    def set_vehicle_profile(self, scope_id: str, profile: dict | None) -> None:
        state = self._states.get(scope_id); target = state.values.get("last_vehicle_target") if state else None
        if not state or not profile or target not in {"a", "b"}: return
        existing = state.values.get(f"vehicle_{target}")
        if isinstance(existing, dict): state.values[f"vehicle_{target}"] = self._vehicle(existing["model_name"], existing["powertrain"], profile)

    def set_official_efficiencies(self, scope_id: str, profile: dict | None) -> None: self.set_vehicle_profile(scope_id, profile)

    def select_vehicle_profile(self, scope_id: str, slot: str, profile: dict) -> str | None:
        """Accept a trusted DB profile only in its matching vehicle-selection state."""
        state = self._states.get(scope_id)
        expected = {"A": "vehicle_model", "B": "vehicle_b_model"}.get(slot)
        if not state or state.stage != expected:
            return None
        powertrain = normalize_powertrain(str(profile.get("drivetrain", "")))
        if not powertrain:
            return None
        target = slot.lower()
        state.values[f"vehicle_{target}"] = self._vehicle(str(profile["model_name"]), powertrain, profile)
        state.values["last_vehicle_target"] = target
        state.stage = "vehicle_b_type" if slot == "A" else "calculation_mode"
        return self.vehicle_selection_reply(scope_id)

    @staticmethod
    def _vehicle_label(vehicle: dict) -> str:
        icon = "⚡" if vehicle["powertrain"] == BEV else "🌱" if vehicle["powertrain"] in {HEV, PHEV} else "🚗"
        suffix = " Hybrid" if vehicle["powertrain"] == HEV else ""
        electric = vehicle["powertrain"] in {BEV, PHEV}; efficiency = vehicle.get("electric_efficiency_km_per_kwh" if electric else "fuel_efficiency_km_per_l")
        detail = f"\n官方{'電耗' if electric else '油耗'}：{float(efficiency):g} {'km/kWh' if electric else 'km/L'}" if isinstance(efficiency, (int, float)) else "\n官方效率資料尚缺，稍後會請你補充。"
        return f"{icon} {vehicle['model_name']}{suffix}{detail}"

    def vehicle_selection_reply(self, scope_id: str) -> str:
        state = self._states[scope_id]; target = state.values["last_vehicle_target"]; vehicle = state.values[f"vehicle_{target}"]
        assert isinstance(vehicle, dict)
        if target == "a": return f"第一台已選：\n{self._vehicle_label(vehicle)}\n\n{self._prompts['vehicle_b_type']}"
        a = state.values["vehicle_a"]
        return f"這次幫你比較：\n\n{self._vehicle_label(a)}\nvs\n{self._vehicle_label(vehicle)}\n\n官方能源效率已自動帶入。\n{self._prompts['calculation_mode']}"

    def update_mileage(self, scope_id: str, monthly_km: float) -> str:
        state = self._states[scope_id]; previous = state.values.get("monthly_km"); state.values["monthly_km"] = monthly_km
        if state.stage == "cost_result":
            if previous == monthly_km:
                return "里程我已經記下來了；目前顯示的是這組條件的試算結果。"
            result = self._calculate(state.values)
            state.values["current_result"] = result
            return "收到，我已更新里程資料並重新計算。\n" + result
        if previous == monthly_km: return "里程我已經記下來了，目前還差充電方式。\n" + self._prompt_for(state)
        return "收到，我已更新里程資料。\n" + self._prompt_for(state)

    def request_actual_efficiency(self, scope_id: str, text: str) -> str:
        """Honor an explicit request to override a known official efficiency."""
        state = self._states[scope_id]
        wants_electric = "電耗" in text or "電" in text
        candidates = []
        for target in ("a", "b"):
            vehicle = state.values.get(f"vehicle_{target}")
            if isinstance(vehicle, dict) and vehicle["powertrain"] in ({BEV, PHEV} if wants_electric else {ICE_GASOLINE, ICE_DIESEL, HEV, PHEV}):
                candidates.append((target, vehicle))
        if "第一" in text: candidates = [item for item in candidates if item[0] == "a"]
        if "第二" in text: candidates = [item for item in candidates if item[0] == "b"]
        if len(candidates) != 1:
            labels = [f"{'A' if target == 'a' else 'B'}. {vehicle['model_name']}" for target, vehicle in candidates]
            return "請指定要覆寫哪一台車的效率：\n" + "\n".join(labels or ["請先完成兩台車款選擇。"])
        target, vehicle = candidates[0]
        state.values["resume_stage_after_efficiency_override"] = state.stage
        state.stage = f"vehicle_{target}_{'electric' if wants_electric else 'fuel'}_efficiency"
        return f"沒問題，將改用 {vehicle['model_name']} 的實際{'電耗' if wants_electric else '油耗'}。\n{self._prompt_for(state)}"

    @staticmethod
    def parse_calculation_mode(message: str) -> str | None:
        """Accept both LINE postback values and natural wording at this state."""
        compact = message.strip().casefold().replace(" ", "")
        if compact in {"quick", "快速", "快速試算", "快速算"}:
            return "quick"
        if compact in {"advanced", "精準", "精準試算", "詳細", "完整輸入"}:
            return "advanced"
        return None

    def advance(self, scope_id: str, value: str) -> str:
        state = self._states[scope_id]; stage, cleaned = state.stage, value.strip().replace(",", "")
        if stage.startswith("full_cost_"):
            return self._advance_full_cost(scope_id, state, cleaned)
        if stage in {"vehicle_type", "vehicle_b_type"}:
            powertrain = normalize_powertrain(cleaned)
            if not powertrain: return self._prompts[stage]
            state.values["pending_powertrain"] = powertrain; state.stage = "vehicle_model" if stage == "vehicle_type" else "vehicle_b_model"; return self._model_prompt(powertrain)
        if stage in {"vehicle_model", "vehicle_b_model"}:
            p = str(state.values["pending_powertrain"]); model = self._match_model(p, cleaned)
            if not model:
                choices = self._model_suggestions(p, cleaned); return f"你是指哪一款呢？可以選「{'」或「'.join(choices)}」。" if choices else self._model_prompt(p)
            target = "a" if stage == "vehicle_model" else "b"; state.values[f"vehicle_{target}"] = self._vehicle(model, p); state.values["last_vehicle_target"] = target; state.stage = "vehicle_b_type" if target == "a" else "calculation_mode"
            return self.vehicle_selection_reply(scope_id)
        if stage == "calculation_mode":
            mode = self.parse_calculation_mode(value)
            if not mode: return self._prompts[stage]
            state.values["calculation_mode"] = mode; state.stage = "monthly_km"; return self._prompt_for(state)
        if stage == "monthly_km":
            number = self._number(cleaned); daily = self._daily_km(cleaned)
            if number is None and daily is None: return "這個里程我還沒看懂。可輸入每月總里程、每天 40 公里，或上下班單程 15 公里。"
            state.values["monthly_km"] = number if number is not None else daily * 30; state.stage = "ownership_years"; return self._prompt_for(state)
        if stage == "ownership_years":
            years = 5 if cleaned in {"使用預設", "預設", "不確定"} else self._years(cleaned)
            if years is None or not 1 <= years <= 15: return "請輸入 1～15 年，例如「10 年」；或回覆「使用預設」。"
            state.values["ownership_years"] = years
            a, b = state.values["vehicle_a"], state.values["vehicle_b"]
            assert isinstance(a, dict) and isinstance(b, dict)
            if PHEV in {a["powertrain"], b["powertrain"]}:
                state.stage = "phev_preset"; return self._prompt_for(state)
            if state.values.get("calculation_mode") == "quick":
                self._apply_quick_defaults(state); return self._next_field(scope_id, state)
            self._prepare_fields(state); return self._next_field(scope_id, state)
        if stage == "phev_preset":
            if cleaned == "custom" and state.values.get("calculation_mode") == "advanced":
                state.stage = "phev_electric_share"; return self._prompt_for(state)
            try: ratio = float(cleaned)
            except ValueError: return self._prompts[stage]
            if ratio not in {0.2, 0.5, 0.8}: return self._prompts[stage]
            state.values["phev_electric_share"] = ratio
            if state.values.get("calculation_mode") == "quick": self._apply_quick_defaults(state); return self._next_field(scope_id, state)
            self._prepare_fields(state); return self._next_field(scope_id, state)
        if stage == "charging_ratio":
            parsed = self._charging.parse(cleaned)
            if not parsed: return self._charging.clarification_reply()
            state.values.update(home_charge_ratio=parsed.home_charge_ratio, public_charge_ratio=parsed.public_charge_ratio); return parsed.reply + "\n" + self._next_field(scope_id, state)
        if stage in {"home_electricity_price", "public_charging_price"}:
            defaults = {"home_electricity_price": 3.5, "public_charging_price": 8.0}; n = defaults[stage] if cleaned in {"使用預設", "預設", "不確定"} else self._number(cleaned)
            if n is None or n <= 0: return "請輸入大於 0 的金額，或回覆「使用預設」。"
            state.values[stage] = n; return self._next_field(scope_id, state)
        if stage == "phev_electric_share":
            n = self._number(cleaned)
            if n is None or not 0 <= n <= 100: return "請輸入 0～100，例如 60。"
            state.values[stage] = n / 100; return self._next_field(scope_id, state)
        if stage.endswith("_fuel_efficiency") or stage.endswith("_electric_efficiency"):
            n = self._number(cleaned)
            if n is None or n <= 0: return "請輸入大於 0 的效率數字。"
            target = "a" if "vehicle_a" in stage else "b"; vehicle = state.values[f"vehicle_{target}"]; assert isinstance(vehicle, dict)
            vehicle["fuel_efficiency_km_per_l" if stage.endswith("fuel_efficiency") else "electric_efficiency_km_per_kwh"] = n
            resume = state.values.pop("resume_stage_after_efficiency_override", None)
            if isinstance(resume, str):
                state.stage = resume
                return "已更新實際效率。\n" + self._prompt_for(state)
            return self._next_field(scope_id, state)
        return self._prompt_for(state)

    def _prepare_fields(self, state: CostFlowState) -> None:
        a, b = state.values["vehicle_a"], state.values["vehicle_b"]; assert isinstance(a, dict) and isinstance(b, dict)
        fields = derive_required_inputs(a, b)[2:]
        if "fuel_price" in fields:
            quote = self._fuel_prices.latest_95_unleaded()
            if quote: state.values["fuel_price"] = quote.price_per_liter
            fields.remove("fuel_price")
        state.values["pending_fields"] = fields

    def _apply_quick_defaults(self, state: CostFlowState) -> None:
        quote = self._fuel_prices.latest_95_unleaded()
        if quote: state.values["fuel_price"] = quote.price_per_liter
        state.values.update(home_charge_ratio=0.8, public_charge_ratio=0.2, home_electricity_price=3.5, public_charging_price=8.0)
        a, b = state.values["vehicle_a"], state.values["vehicle_b"]
        assert isinstance(a, dict) and isinstance(b, dict)
        # Quick mode supplies pricing assumptions, not missing vehicle
        # specifications.  Unknown BEV/PHEV electric efficiency (or ICE/HEV
        # fuel efficiency) must still be collected before arithmetic begins.
        state.values["pending_fields"] = [
            field for field in derive_required_inputs(a, b)[2:]
            if field.endswith(("_fuel_efficiency", "_electric_efficiency"))
        ]

    def _next_field(self, scope_id: str, state: CostFlowState) -> str:
        pending = state.values.get("pending_fields", []); assert isinstance(pending, list)
        while pending:
            stage = pending.pop(0)
            if stage == "home_electricity_price" and not state.values.get("home_charge_ratio"): continue
            if stage == "public_charging_price" and not state.values.get("public_charge_ratio"): continue
            state.stage = stage; return self._prompt_for(state)
        state.stage = "cost_result"
        state.values.setdefault("calculation_id", str(uuid.uuid4()))
        result = self._calculate(state.values)
        state.values["current_result"] = result
        self._followups[scope_id] = self._ownership_followup(int(state.values["ownership_years"]))
        return result

    def _prompt_for(self, state: CostFlowState) -> str:
        if state.stage in {"vehicle_model", "vehicle_b_model"}: return self._model_prompt(str(state.values["pending_powertrain"]))
        if state.stage.endswith("_fuel_efficiency"): return "資料庫沒有這款車的官方油耗；請輸入實際平均油耗（km/L）。"
        if state.stage.endswith("_electric_efficiency"): return "資料庫沒有這款車的官方電耗；請輸入實際平均電耗（km/kWh）。"
        return self._prompts[state.stage]

    def _advance_full_cost(self, scope_id: str, state: CostFlowState, cleaned: str) -> str:
        stage = state.stage
        if stage == "full_cost_residual":
            if cleaned not in {"exclude", "manual"}:
                return self._prompts[stage]
            state.values["full_cost_residual_mode"] = cleaned
            state.stage = "full_cost_a_residual" if cleaned == "manual" else self._first_full_cost_field(state)
            return self._prompt_for_full_cost(state)
        if stage in {"full_cost_a_residual", "full_cost_b_residual"}:
            number = self._number(cleaned)
            if number is None or not 0 <= number <= 100:
                return "請輸入 0～100 的百分比，例如 45。"
            state.values[stage.removeprefix("full_cost_")] = number / 100
            state.stage = "full_cost_b_residual" if stage.endswith("a_residual") else self._first_full_cost_field(state)
            return self._prompt_for_full_cost(state)
        if stage == "full_cost_loan_choice":
            if cleaned == "no":
                state.values["full_cost_loan_enabled"] = False
                return self._finish_full_cost(scope_id, state)
            if cleaned == "yes":
                state.values["full_cost_loan_enabled"] = True
                state.stage = "full_cost_loan_down_payment"
                return self._prompts[state.stage]
            return self._prompts[stage]
        fields = self._full_cost_fields(state)
        number = self._number(cleaned)
        if number is None or number < 0:
            return "請輸入 0 或正數金額。"
        if stage == "full_cost_loan_rate":
            if number > 100: return "請輸入 0～100 的年利率百分比。"
            state.values[stage.removeprefix("full_cost_")] = number / 100
        elif stage == "full_cost_loan_years":
            if number < 1 or number > 15 or number != int(number): return "請輸入 1～15 年。"
            state.values[stage.removeprefix("full_cost_")] = int(number)
        else:
            state.values[stage.removeprefix("full_cost_")] = number
        index = fields.index(stage)
        if index + 1 < len(fields):
            state.stage = fields[index + 1]
            return self._prompt_for_full_cost(state)
        return self._finish_full_cost(scope_id, state)

    def _first_full_cost_field(self, state: CostFlowState) -> str:
        return self._full_cost_fields(state)[0]

    def _full_cost_fields(self, state: CostFlowState) -> list[str]:
        a, b = state.values["vehicle_a"], state.values["vehicle_b"]
        assert isinstance(a, dict) and isinstance(b, dict)
        fields: list[str] = []
        if {ICE_GASOLINE, ICE_DIESEL, HEV, PHEV} & {a["powertrain"], b["powertrain"]} and not state.values.get("fuel_price"):
            fields.append("full_cost_fuel_price")
        if not a.get("purchase_price_ntd"): fields.append("full_cost_a_purchase_price")
        if not b.get("purchase_price_ntd"): fields.append("full_cost_b_purchase_price")
        fields += ["full_cost_a_maintenance", "full_cost_b_maintenance", "full_cost_a_insurance", "full_cost_b_insurance", "full_cost_a_tax", "full_cost_b_tax", "full_cost_a_tire_set", "full_cost_a_tire_life", "full_cost_b_tire_set", "full_cost_b_tire_life", "full_cost_parking", "full_cost_miscellaneous"]
        if {BEV, PHEV} & {a["powertrain"], b["powertrain"]}: fields.append("full_cost_charger")
        fields += ["full_cost_loan_choice", "full_cost_loan_down_payment", "full_cost_loan_rate", "full_cost_loan_years", "full_cost_loan_fee"]
        if state.values.get("full_cost_loan_enabled") is False:
            fields = [field for field in fields if not field.startswith("full_cost_loan_") or field == "full_cost_loan_choice"]
        return fields

    def _prompt_for_full_cost(self, state: CostFlowState) -> str:
        prompt = self._prompts[state.stage]
        if state.stage in {"full_cost_residual", "full_cost_loan_choice"}:
            return prompt
        return prompt

    def _finish_full_cost(self, scope_id: str, state: CostFlowState) -> str:
        state.stage = "full_cost_result"
        state.values["full_cost_result"] = self._calculate_full_tco(state.values)
        return str(state.values["full_cost_result"])

    def _model_prompt(self, p: str) -> str: return f"好，先看{POWERTRAIN_LABELS[p]}。\n目前支援：\n" + "\n".join(self._models_by_powertrain[p])
    def _match_model(self, p: str, value: str) -> str | None:
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.casefold())
        exact = next((m for m in self._models_by_powertrain[p] if m.casefold().replace(" ", "") == normalized), None)
        if exact:
            return exact
        matches = [m for m in self._models_by_powertrain[p] if len(m.casefold().replace(" ", "")) >= 3 and m.casefold().replace(" ", "") in normalized]
        return matches[0] if len(matches) == 1 else None
    def _model_suggestions(self, p: str, value: str) -> tuple[str, ...]:
        normalized = value.casefold().replace(" ", ""); matches = tuple(m for m in self._models_by_powertrain[p] if m.casefold().replace(" ", "").startswith(normalized)); return matches if len(normalized) >= 3 and 1 < len(matches) <= 4 else ()
    @staticmethod
    def _number(v: str) -> float | None:
        m = re.fullmatch(r"(?:約|大約|大概)?\s*(\d+(?:\.\d+)?)\s*(?:公里|km|元|度|%|％|吧|左右)?\s*[？?!！。]?", v, re.I); return float(m.group(1)) if m else None
    @staticmethod
    def _daily_km(v: str) -> float | None:
        m = re.fullmatch(r"(?:每天|每日)\s*(?:約|大約|大概)?\s*(\d+(?:\.\d+)?)\s*(?:公里|km)", v, re.I); return float(m.group(1)) if m else None
    @staticmethod
    def _years(v: str) -> int | None:
        m = re.fullmatch(r"(?:約|大約|大概)?\s*(\d+)\s*年?[？?!！。]?", v); return int(m.group(1)) if m else None
    @staticmethod
    def _ownership_followup(years: int) -> str: return f"這次先以 {years} 年持有估算。想改年限可直接回覆 1～15 年，例如「10 年」。"

    def _calculate(self, values: dict[str, object]) -> str:
        a, b = values["vehicle_a"], values["vehicle_b"]; assert isinstance(a, dict) and isinstance(b, dict)
        yearly, years, fuel = float(values["monthly_km"]) * 12, int(values["ownership_years"]), float(values.get("fuel_price", 0))
        electric = float(values.get("home_charge_ratio", 0)) * float(values.get("home_electricity_price", 0)) + float(values.get("public_charge_ratio", 0)) * float(values.get("public_charging_price", 0))
        def annual(v: dict) -> float:
            electric_efficiency = v.get("electric_efficiency_km_per_kwh")
            fuel_efficiency = v.get("fuel_efficiency_km_per_l")
            if v["powertrain"] == BEV:
                if not isinstance(electric_efficiency, (int, float)) or electric_efficiency <= 0:
                    raise ValueError(f"{v['model_name']} 缺少有效官方電耗，請先補充 km/kWh。")
                return yearly / float(electric_efficiency) * electric
            if v["powertrain"] == PHEV:
                if not isinstance(electric_efficiency, (int, float)) or electric_efficiency <= 0:
                    raise ValueError(f"{v['model_name']} 缺少有效官方電耗，請先補充 km/kWh。")
                if not isinstance(fuel_efficiency, (int, float)) or fuel_efficiency <= 0:
                    raise ValueError(f"{v['model_name']} 缺少有效官方油耗，請先補充 km/L。")
                share = float(values.get("phev_electric_share", .5)); return yearly*(1-share)/float(fuel_efficiency)*fuel + yearly*share/float(electric_efficiency)*electric
            if not isinstance(fuel_efficiency, (int, float)) or fuel_efficiency <= 0:
                raise ValueError(f"{v['model_name']} 缺少有效官方油耗，請先補充 km/L。")
            return yearly / float(fuel_efficiency) * fuel
        ca, cb = annual(a), annual(b); assumptions = f"・年行駛里程：約 {yearly:,.0f} 公里\n"
        if electric: assumptions += f"・充電假設：家充 {float(values.get('home_charge_ratio', 0)):.0%}／公共 {float(values.get('public_charge_ratio', 0)):.0%}；平均 {electric:.1f} 元/度\n"
        if fuel: assumptions += f"・油價：{fuel:.1f} 元/L\n"
        annual_difference = abs(ca - cb)
        phev_note = f"・PHEV 純電使用比例：{float(values.get('phev_electric_share', 0)):.0%}\n" if PHEV in {a['powertrain'], b['powertrain']} else ""
        explanation = "以電代油的里程比例與充電成本" if electric else "兩車官方油耗與油價"
        return f"💰 {years} 年能源成本比較\n\n比較車款：\n{self._vehicle_label(a)}\n\n{self._vehicle_label(b)}\n\n{assumptions}{phev_note}・{a['model_name']}：約 NT$ {ca:,.0f}／年\n・{b['model_name']}：約 NT$ {cb:,.0f}／年\n・每年約差：NT$ {annual_difference:,.0f}\n・{years} 年累積約差：NT$ {annual_difference * years:,.0f}\n\n為什麼有差？主要來自{explanation}。\n※ 僅比較能源成本，不代表完整總持有成本。"

    def _calculate_full_tco(self, values: dict[str, object]) -> str:
        a, b = values["vehicle_a"], values["vehicle_b"]
        assert isinstance(a, dict) and isinstance(b, dict)

        def profile(slot: str, vehicle: dict) -> VehicleTcoProfile:
            price = values.get(f"{slot}_purchase_price", vehicle.get("purchase_price_ntd", 0))
            return VehicleTcoProfile(
                name=str(vehicle["model_name"]), powertrain=str(vehicle["powertrain"]), purchase_price=float(price or 0),
                fuel_efficiency=vehicle.get("fuel_efficiency_km_per_l"), electric_efficiency=vehicle.get("electric_efficiency_km_per_kwh"),
                annual_maintenance=float(values.get(f"{slot}_maintenance", 0)), annual_insurance=float(values.get(f"{slot}_insurance", 0)),
                annual_tax=float(values.get(f"{slot}_tax", 0)), tire_set_price=float(values.get(f"{slot}_tire_set", 0)),
                tire_lifespan_km=float(values.get(f"{slot}_tire_life", 0)),
                residual_rates={"manual": float(values.get(f"{slot}_residual", 0))} if values.get("full_cost_residual_mode") == "manual" else {},
            )

        loan = LoanTerms(
            enabled=bool(values.get("full_cost_loan_enabled")), down_payment=float(values.get("loan_down_payment", 0)),
            annual_interest_rate=float(values.get("loan_rate", 0)), years=int(values.get("loan_years", 0)), fee=float(values.get("loan_fee", 0)),
        )
        inputs = TcoInputs(
            annual_mileage=float(values["monthly_km"]) * 12, ownership_years=int(values["ownership_years"]),
            fuel_price_per_liter=float(values.get("fuel_price", 0)) or None,
            home_electricity_price=float(values.get("home_electricity_price", 0)) or None,
            public_electricity_price=float(values.get("public_charging_price", 0)) or None,
            home_charge_ratio=float(values.get("home_charge_ratio", 1)), public_charge_ratio=float(values.get("public_charge_ratio", 0)),
            phev_electric_mileage_ratio=float(values.get("phev_electric_share", 0)), annual_parking=float(values.get("parking", 0)),
            annual_miscellaneous=float(values.get("miscellaneous", 0)), charger_installation_cost=float(values.get("charger", 0)), loan=loan,
            residual_scenario="manual" if values.get("full_cost_residual_mode") == "manual" else "exclude",
        )
        result = TcoCalculator().compare(profile("a", a), profile("b", b), inputs)
        va, vb = result.vehicle_a, result.vehicle_b
        cheaper = va.name if va.total_cost <= vb.total_cost else vb.name
        difference = abs(result.total_difference)
        def line_items(item: object) -> list[dict[str, object]]:
            components = getattr(item, "components")
            return [{"category": key, "label": label, "value": components.get(key), "status": "calculated"} for label, key in FULL_TCO_CATEGORIES]
        def breakdown(item: object) -> str:
            return "\n".join(f"・{entry['label']}：{format_full_tco_component(entry['value'], str(entry['status']))}" for entry in line_items(item))
        values["full_tco_line_items"] = {"vehicle_a": line_items(va), "vehicle_b": line_items(vb)}
        residual_note = "已依你的情境假設納入期末殘值；不代表保證售價。" if inputs.residual_scenario == "manual" else "未納入期末殘值，避免在沒有可靠依據時推測。"
        loan_note = "貸款以兩車相同條件估算。" if loan.enabled else "未納入貸款成本。"
        return f"💰 {inputs.ownership_years} 年完整持有成本比較\n\n比較車款：{va.name} vs {vb.name}\n\n結論：{cheaper} 總持有成本約少 NT$ {difference:,.0f}\n\n・{va.name}：NT$ {va.total_cost:,.0f}\n{breakdown(va)}\n\n・{vb.name}：NT$ {vb.total_cost:,.0f}\n{breakdown(vb)}\n\n假設：年行駛 {inputs.annual_mileage:,.0f} km；{residual_note}\n{loan_note}\n※ 此為依你輸入條件的情境試算，非報價、保證或購車建議。"

    def switch_vehicle_if_corrected(self, scope_id: str, text: str) -> tuple[str, str] | None:
        if scope_id not in self._states or not any(x in text for x in ("講錯", "改成", "其實", "應該是")): return None
        cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", text.casefold().replace(" ", ""))
        for marker in ("講錯了", "講錯", "改成", "其實是", "其實", "應該是", "車型", "車款", "車"): cleaned = cleaned.replace(marker, "")
        matches = [(m, p) for p, models in self._models_by_powertrain.items() for m in models if m.casefold().replace(" ", "") == cleaned or m.casefold().replace(" ", "").startswith(cleaned)]
        if len(matches) != 1: return None
        model, p = matches[0]; state = self._states[scope_id]; state.values["vehicle_a"] = self._vehicle(model, p); state.values["last_vehicle_target"] = "a"; state.stage = "vehicle_b_type"; return model, p
    def resume_after_vehicle_switch(self, scope_id: str) -> str: return self.vehicle_selection_reply(scope_id)


cost_flow_manager = CostFlowManager()
