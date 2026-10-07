from app.services.cost_result_flex import build_cost_result_flex, build_share_card
from app.services.vehicle_carousel import build_vehicle_carousel, collapse_equivalent_profiles


def test_vehicle_carousel_shows_the_trim_needed_to_distinguish_profiles() -> None:
    flex = build_vehicle_carousel([{
        "id": "vehicle-1", "model_name": "bZ4X", "trim_name": "旗艦", "drivetrain": "ev",
        "electric_efficiency_km_per_kwh": 6.7, "purchase_price_ntd": 1280000,
    }], "A")
    bubble = flex["contents"]["contents"][0]
    text = " ".join(item.get("text", "") for item in bubble["body"]["contents"])
    assert "bZ4X" in text and "純電" in text and "6.7 km/kWh" in text and "1,280,000" in text
    assert "等級：旗艦" in text
    assert bubble["footer"]["contents"][0]["action"]["data"] == "action=select_vehicle&slot=A&vehicle_id=vehicle-1"


def test_equivalent_trims_are_merged_but_distinct_models_are_not() -> None:
    vehicles = [
        {"id": "cross-standard", "model_name": "COROLLA CROSS", "trim_name": "豪華", "drivetrain": "gasoline", "fuel_efficiency_km_per_l": 14.3, "purchase_price_ntd": 800000},
        {"id": "cross-option", "model_name": "COROLLA CROSS", "trim_name": "豪華（選）", "drivetrain": "gasoline", "fuel_efficiency_km_per_l": 14.3, "purchase_price_ntd": 820000},
        {"id": "vios", "model_name": "VIOS", "drivetrain": "gasoline", "fuel_efficiency_km_per_l": 14.3, "purchase_price_ntd": 600000},
        {"id": "yaris", "model_name": "YARIS CROSS", "drivetrain": "gasoline", "fuel_efficiency_km_per_l": 14.3, "purchase_price_ntd": 650000},
    ]
    merged = collapse_equivalent_profiles(vehicles)
    assert {vehicle["id"] for vehicle in merged} == {"cross-standard", "vios", "yaris"}
    cross = next(vehicle for vehicle in merged if vehicle["id"] == "cross-standard")
    assert cross["display_trim_summary"] == "豪華、豪華（選）"
    flex = build_vehicle_carousel(vehicles, "A")
    assert len(flex["contents"]["contents"]) == 3
    cross_card = next(card for card in flex["contents"]["contents"] if card["footer"]["contents"][0]["action"]["data"].endswith("cross-standard"))
    assert "等級：豪華、豪華（選）" in str(cross_card)


def test_cost_result_is_presented_as_flex() -> None:
    flex = build_cost_result_flex("💰 8 年能源成本比較\n🌱 CROWN Hybrid\n🔌 CROWN SPORT PHEV\n・年行駛里程：約 13,800 公里\n・充電假設：家充 80%／公共 20%\n・CROWN Hybrid：約 NT$ 161,164／年\n・CROWN SPORT PHEV：約 NT$ 86,774／年\n・每年約差：NT$ 74,390\n・8 年累積約差：NT$ 595,120\n※ 僅比較能源成本，不代表完整總持有成本。")
    assert flex["type"] == "flex"
    assert flex["contents"]["type"] == "bubble"
    contents = flex["contents"]["body"]["contents"]
    assert contents[0]["text"] == "💰 8 年能源成本比較"
    assert "NT$ 74,390" == contents[3]["contents"][1]["text"]
    assert any(item.get("text") == "計算假設" for item in contents)
    assert len(flex["contents"]["footer"]["contents"]) == 4


def test_group_result_footer_generates_share_card_without_group_reshare() -> None:
    flex = build_cost_result_flex("💰 5 年能源成本比較\n※ 僅比較能源成本。", "calculation-id", "group")
    buttons = flex["contents"]["footer"]["contents"]
    assert buttons[-2]["action"]["label"] == "產生分享卡"
    assert buttons[-2]["action"]["data"] == "action=generate_share_card&calculation_id=calculation-id"
    assert buttons[-1]["action"]["data"] == "action=show_service_menu"
    assert all("share_to_group" not in button["action"]["data"] for button in buttons)


def test_share_card_is_compact_and_has_no_personal_financial_details() -> None:
    flex = build_share_card("💰 8 年能源成本比較\n🌱 VIOS\n⚡ bZ4X\n・VIOS：約 NT$ 26,084／年\n・bZ4X：約 NT$ 8,136／年\n・每年約差：NT$ 17,949\n・8 年累積約差：NT$ 143,589\n※ 僅比較能源成本")
    assert flex["type"] == "flex"
    text = str(flex)
    assert "貸款" not in text and "頭期款" not in text
    assert "每年約差：NT$ 17,949" in text
