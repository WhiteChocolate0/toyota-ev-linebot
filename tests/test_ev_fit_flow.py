from app.services.ev_fit_flex import build_ev_fit_flex
from app.services.ev_fit_flow import EvFitManager


def test_ev_fit_uses_life_first_order_and_returns_a_clear_summary() -> None:
    flow = EvFitManager()
    opening = flow.start("u")
    assert "每天大約開多少公里" in opening
    for answer in ("20_40", "monthly", "accept", "yes", "NEED_CONFIRMATION", "HOME_CHARGE_DONE", "yes"):
        result = flow.advance("u", answer)
    assert "我適合開電動車嗎？" in result
    assert "✅ 日常里程：適合" in result
    assert "🟡 家庭補電：待確認" in result
    assert "最需要確認" in result
    assert "不構成購車建議" in result


def test_no_parking_skips_home_charging_question() -> None:
    flow = EvFitManager(); flow.start("u")
    for answer in ("under_20", "rare", "accept", "no"):
        prompt = flow.advance("u", answer)
    assert "工作地點" in prompt
    assert flow._states["u"].values["home_charge"] == "UNAVAILABLE"


def test_home_110v_is_evaluated_against_daily_mileage_and_uses_official_feature() -> None:
    flow = EvFitManager(home_110v_good_max_daily_km=40, home_110v_warning_max_daily_km=80)
    flow.start("short")
    for answer in ("20_40", "rare", "accept", "yes", "HOME_110V", "HOME_CHARGE_DONE", "yes"):
        result = flow.advance("short", answer, "bZ4X 隨車附原廠 AC 充電線，可連接一般家用 110V 插座充電")
    assert "✅ 家庭補電：110V 可作日常補電" in result
    assert "💡 bZ4X 補電彈性" in result
    assert "原廠 AC 充電線" in result

    flow.start("medium")
    for answer in ("60_100", "rare", "accept", "yes", "HOME_110V", "HOME_CHARGE_DONE", "yes"):
        result = flow.advance("medium", answer)
    assert "🟡 家庭補電：110V 可補電，建議確認 220V" in result
    assert "最需要確認：家中是否能進一步安裝 220V 充電設備" in result

    flow.start("high")
    for answer in ("over_100", "rare", "accept", "yes", "HOME_110V", "HOME_CHARGE_DONE", "yes"):
        result = flow.advance("high", answer)
    assert "❗ 家庭補電：110V 不適合作為主要補電" in result


def test_ev_fit_card_has_textual_statuses_blocker_and_cost_cta() -> None:
    card = build_ev_fit_flex("我適合開電動車嗎？\n\n你的日常用車條件大致適合 EV，但家用充電條件還需要先確認。\n\n✅ 日常里程：適合\n🟡 家庭補電：110V 可補電，建議確認 220V\n✅ 長途需求：可規劃\n◻️ 工作地補電：不列入日常假設\n\n最需要確認：家中是否能進一步安裝 220V 充電設備\n\n下一步：確認充電條件後，可以再比較 EV 與油車的長期使用成本。\n\n💡 bZ4X 補電彈性\nbZ4X 隨車附原廠 AC 充電線，可連接一般家用 110V 插座充電；若每日里程較高，220V 充電設備會更適合。")
    assert card["type"] == "flex"
    body = str(card["contents"]["body"])
    assert "✅ 日常里程：適合" in body and "最需要確認" in body and "bZ4X 補電彈性" in body
    assert card["contents"]["footer"]["contents"][0]["action"]["label"] == "比較用車成本"


def test_home_charging_sources_can_be_selected_multiple_times_before_done() -> None:
    flow = EvFitManager(); flow.start("multi")
    for answer in ("20_40", "monthly", "accept", "yes"):
        flow.advance("multi", answer)
    assert "目前已選" in flow.advance("multi", "HOME_110V")
    assert "目前已選" in flow.advance("multi", "HOME_220V")
    flow.advance("multi", "HOME_CHARGE_DONE")
    assert flow._states["multi"].values["home_charge"] == "HOME_220V"
    assert "HOME_110V" in flow._states["multi"].values["home_charge_sources"]
