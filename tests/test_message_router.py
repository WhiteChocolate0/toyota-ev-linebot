from app.services.message_router import route_text_message
from app.services.faq_templates import source_id_for


def test_unrelated_group_message_is_not_answered() -> None:
    assert route_text_message("晚餐想吃什麼？", "group") is None


def test_group_battery_question_is_answered() -> None:
    reply = route_text_message("電池壞掉是不是很貴？", "group")
    assert reply is not None
    assert "保固" in reply.text


def test_group_question_without_question_mark_is_answered() -> None:
    reply = route_text_message("電池可以用多久", "group")
    assert reply is not None
    assert reply.concern_code == "BATTERY"


def test_cost_quick_reply_starts_calculator_flow() -> None:
    reply = route_text_message("我想做成本試算", "group")
    assert reply is not None
    assert "長期用車能源成本" in reply.text


def test_general_ev_and_toyota_questions_are_not_silent() -> None:
    for text, expected_topic in (
        ("EV 是什麼？", "EV_BASIC"),
        ("Toyota 品牌很好嗎？", "TOYOTA_BRAND"),
        ("油車還能開", "ICE_FUTURE"),
        ("電車有什麼好處", "EV_GENERAL_OPINION"),
        ("Toyota 電車有什麼優勢", "TOYOTA_EV"),
    ):
        reply = route_text_message(text, "group")
        assert reply is not None
        assert reply.concern_code == expected_topic


def test_new_knowledge_sources_are_selected_by_topic_and_vehicle_context() -> None:
    assert source_id_for("EV_BASIC", "EV 是什麼？") == "src_ev_bev_definition"
    assert source_id_for("EV_BASIC", "HEV 油電是什麼？") == "src_hev_definition"
    assert source_id_for("EV_BASIC", "PHEV 是什麼？") == "src_phev_definition"
    assert source_id_for("EV_VS_HEV", "電車跟油電怎麼選") == "src_bev_vs_hev"
    assert source_id_for("ICE_FUTURE", "油車還能開嗎") == "src_tw_ice_existing_cars"
    assert source_id_for("TOYOTA_BRAND", "Toyota 品牌好嗎") == "src_toyota_brand_neutral"
    assert source_id_for("POLICY", "2040 新車政策") == "src_tw_2040_new_car_electrification"
    assert source_id_for("CHARGING", "bZ4X 家裡 110V 能充嗎") == "src_faq_home_charging_needed"
    assert source_id_for("BZ4X", "bZ4X 家裡 110V 能充嗎") == "src_faq_home_charging_needed"
    assert source_id_for("BZ4X", "bZ4X 用什麼 CCS1 接頭？") == "src_bz4x_charge_connector"
    assert source_id_for("BZ4X", "bZ4X 743 公里是實際續航嗎？") == "src_bz4x_range_realworld"
    assert source_id_for("BATTERY", "bZ4X 8 年後電池就壞嗎？") == "src_faq_battery_8years"
    assert source_id_for("EV_BASIC", "HEV 動能回收是什麼？") == "src_hev_regenerative_braking"
    assert source_id_for("POLICY", "電動車牌照稅免到何時？") == "src_tw_ev_license_tax_exemption"
    assert source_id_for("POLICY", "電動車燃料費怎麼算？") == "src_tw_ev_road_fee_exemption"
