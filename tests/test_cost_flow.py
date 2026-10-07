from app.services.cost_flow import CostFlowManager, derive_required_inputs, format_full_tco_component
from app.services.flow_intent import route_flow_intent
from app.services.mileage_parser import MileageParser
from app.services.powertrain import BEV, HEV, ICE_GASOLINE, parse_powertrain


def vehicle(powertrain: str, *, fuel: float | None = None, electric: float | None = None) -> dict:
    return {"id": "id", "model_name": "Test", "trim_name": None, "powertrain": powertrain,
            "purchase_price_ntd": 1, "fuel_efficiency_km_per_l": fuel,
            "electric_efficiency_km_per_kwh": electric}


def select_pair(flow: CostFlowManager, scope: str = "u") -> None:
    flow.start(scope)
    flow.advance(scope, "油電"); flow.advance(scope, "COROLLA CROSS")
    flow.set_vehicle_profile(scope, {"id": "a", "model_name": "COROLLA CROSS", "drivetrain": "hybrid", "fuel_efficiency_km_per_l": 23.5})
    flow.advance(scope, "電車"); flow.advance(scope, "bZ4X")
    flow.set_vehicle_profile(scope, {"id": "b", "model_name": "bZ4X", "drivetrain": "ev", "electric_efficiency_km_per_kwh": 6.7})


def test_powertrain_synonyms_are_parsed() -> None:
    assert parse_powertrain("電")["powertrain"] == BEV
    assert parse_powertrain("電車")["powertrain"] == BEV
    assert parse_powertrain("油電")["powertrain"] == HEV


def test_vehicle_selection_state_does_not_run_mileage_parser() -> None:
    flow = CostFlowManager(); flow.start("strict")
    assert route_flow_intent("電").intent == "answer_current_field"
    reply = flow.advance("strict", "電")
    assert "純電車" in reply and flow.current_stage("strict") == "vehicle_model"
    flow.start("strict-2")
    reply = flow.advance("strict-2", "每天5公里")
    assert "動力" in reply
    assert "monthly_km" not in flow._states["strict-2"].values


def test_model_selection_only_accepts_model_and_has_quick_replies() -> None:
    flow = CostFlowManager(); flow.start("models")
    flow.advance("models", "HEV")
    assert any(item["action"]["data"] == "model=ALTIS" for item in flow.quick_reply_items("models"))
    reply = flow.advance("models", "目前的車款是Altis")
    assert "第一台已選" in reply
    assert flow.current_stage("models") == "vehicle_b_type"


def test_mileage_is_routed_before_charging_state_parser() -> None:
    flow = CostFlowManager(); select_pair(flow)
    flow.advance("u", "quick"); flow.advance("u", "1200"); flow.advance("u", "5")
    assert flow._states["u"].stage == "cost_result"
    parsed = MileageParser(api_key="").parse("每天20公里")
    assert parsed and parsed.monthly_mileage == 600
    reply = flow.update_mileage("u", parsed.monthly_mileage)
    assert "已更新里程" in reply and "能源成本比較" in reply


def test_known_bz4x_efficiency_skips_manual_electric_efficiency() -> None:
    flow = CostFlowManager(); select_pair(flow)
    flow.advance("u", "quick"); flow.advance("u", "1200")
    reply = flow.advance("u", "5")
    assert "能源成本比較" in reply
    assert "請輸入實際平均電耗" not in reply
    assert flow._states["u"].values["vehicle_b"]["electric_efficiency_km_per_kwh"] == 6.7


def test_quick_mode_collects_missing_efficiency_before_calculating() -> None:
    flow = CostFlowManager(); select_pair(flow)
    flow._states["u"].values["vehicle_b"]["electric_efficiency_km_per_kwh"] = None
    flow.advance("u", "quick"); flow.advance("u", "1200")
    reply = flow.advance("u", "5")
    assert flow.current_stage("u") == "vehicle_b_electric_efficiency"
    assert "請輸入實際平均電耗" in reply


def test_user_can_explicitly_override_known_official_efficiency() -> None:
    flow = CostFlowManager(); select_pair(flow)
    reply = flow.request_actual_efficiency("u", "我要用第二台實際電耗")
    assert "實際電耗" in reply
    assert flow.current_stage("u") == "vehicle_b_electric_efficiency"
    flow.advance("u", "6.2")
    assert flow._states["u"].values["vehicle_b"]["electric_efficiency_km_per_kwh"] == 6.2


def test_vehicle_change_replaces_complete_vehicle_and_powertrain() -> None:
    flow = CostFlowManager(); flow.start("u")
    flow.advance("u", "柴油車"); flow.advance("u", "LAND CRUISER")
    assert flow.switch_vehicle_if_corrected("u", "改成 YARiS CROSS") == ("YARiS CROSS", ICE_GASOLINE)
    assert flow._states["u"].values["vehicle_a"]["powertrain"] == ICE_GASOLINE


def test_conflicting_mileage_requires_clarification() -> None:
    parsed = MileageParser(api_key="").parse("每天20公里、上下班單程15公里")
    assert parsed and parsed.status == "need_clarification"
    assert "想確認一下" in parsed.reply


def test_powertrain_field_planner() -> None:
    hev_bev = derive_required_inputs(vehicle(HEV, fuel=23.5), vehicle(BEV, electric=6.7))
    assert {"fuel_price", "charging_ratio", "home_electricity_price", "public_charging_price"} <= set(hev_bev)
    assert "fuel_price" not in derive_required_inputs(vehicle(BEV, electric=6), vehicle(BEV, electric=7))
    ice_hev = derive_required_inputs(vehicle(ICE_GASOLINE, fuel=15), vehicle(HEV, fuel=23))
    assert "charging_ratio" not in ice_hev and "home_electricity_price" not in ice_hev


def test_full_vehicle_objects_and_pair_confirmation() -> None:
    flow = CostFlowManager(); select_pair(flow); state = flow._states["u"]
    assert set(state.values["vehicle_a"]) == {"id", "model_name", "trim_name", "powertrain", "purchase_price_ntd", "fuel_efficiency_km_per_l", "electric_efficiency_km_per_kwh"}
    reply = flow.vehicle_selection_reply("u")
    assert "23.5 km/L" in reply and "6.7 km/kWh" in reply


def test_result_actions_use_same_calculation_and_vary_by_source_context() -> None:
    flow = CostFlowManager(); select_pair(flow)
    flow.advance("u", "quick"); flow.advance("u", "1200"); flow.advance("u", "5")
    calculation_id = flow.calculation_id("u")
    menu = flow.result_action("u", "edit_cost_inputs", {"calculation_id": [calculation_id]}, "user")
    assert menu and menu[0] == "想調整哪一項？"
    labels = [item["action"]["label"] for item in menu[1]]
    assert "油價" in labels and "充電比例" in labels
    assert flow.result_action("u", "edit_field", {"calculation_id": [calculation_id], "field": ["mileage"]}, "user")
    result = flow.apply_edit("u", "1500")
    assert result and flow.calculation_id("u") == calculation_id

    group_menu = flow.result_action("u", "share_result", {"calculation_id": [calculation_id]}, "group")
    assert group_menu
    group_labels = [item["action"]["label"] for item in group_menu[1]]
    assert {"產生分享卡", "複製摘要", "儲存試算結果"} <= set(group_labels)
    assert "分享到群組" not in group_labels

    user_menu = flow.result_action("u", "share_result", {"calculation_id": [calculation_id]}, "user")
    assert user_menu
    user_labels = [item["action"]["label"] for item in user_menu[1]]
    assert {"產生分享卡", "分享給家人", "邀請我進家庭群組"} <= set(user_labels)


def test_full_tco_conversation_collects_costs_and_returns_a_full_result() -> None:
    flow = CostFlowManager(); select_pair(flow)
    flow.set_vehicle_profile("u", {"id": "a", "model_name": "COROLLA CROSS", "drivetrain": "hybrid", "purchase_price_ntd": 900_000, "fuel_efficiency_km_per_l": 23.5})
    flow.set_vehicle_profile("u", {"id": "b", "model_name": "bZ4X", "drivetrain": "ev", "purchase_price_ntd": 1_280_000, "electric_efficiency_km_per_kwh": 6.7})
    flow.advance("u", "quick"); flow.advance("u", "1200"); flow.advance("u", "5")
    cid = flow.calculation_id("u")
    prompt = flow.result_action("u", "add_full_cost_data", {"calculation_id": [cid]}, "user")
    assert prompt and flow.current_stage("u") == "full_cost_residual"
    assert "殘值" in prompt[0]
    # Exclude residuals, provide a missing first-car price, annual costs for both cars, omit tyres/parking/misc,
    # add EV charger cost, then use the same loan terms for both scenarios.
    answers = ["exclude", "32", "900000", "8000", "12000", "18000", "18000", "0", "12000", "20000", "40000", "20000", "40000", "0", "0", "30000", "yes", "300000", "2.5%", "5", "3000"]
    reply = ""
    for answer in answers:
        reply = flow.advance("u", answer)
    assert flow.current_stage("u") == "full_cost_result"
    assert "完整持有成本比較" in reply
    assert "保養" in reply and "貸款利息" in reply and "充電設備" in reply
    snapshot = flow.calculation_snapshot("u")
    assert snapshot and "完整持有成本比較" in snapshot["current_result"]["text"]
    items = snapshot["current_result"]["line_items"]
    assert [item["category"] for item in items["vehicle_a"]] == [item["category"] for item in items["vehicle_b"]]
    assert next(item for item in items["vehicle_a"] if item["category"] == "charger_installation")["value"] == 0


def test_full_tco_component_statuses_distinguish_zero_missing_and_not_applicable() -> None:
    assert format_full_tco_component(0, "calculated") == "NT$ 0"
    assert format_full_tco_component(None, "missing_input") == "尚未納入"
    assert format_full_tco_component(None, "not_applicable") == "不適用"


def test_expired_user_owned_flow_can_be_paused_and_resumed() -> None:
    flow = CostFlowManager(); flow.start("owner", group_id="G001", owner_user_id="U123")
    last_activity = float(flow._states["owner"].values["last_activity_at"])
    assert flow.pause_if_expired("owner", now=last_activity + flow.flow_timeout_seconds + 1)
    assert flow.is_paused("owner")
    assert "動力" in (flow.resume("owner") or "")
    assert flow.is_active("owner")
