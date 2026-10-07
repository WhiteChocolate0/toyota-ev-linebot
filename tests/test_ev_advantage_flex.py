from app.services.ev_advantage_flex import EV_TAX_BENEFIT_DETAIL, build_ev_tax_benefit_flex


def test_ev_tax_benefit_flex_uses_tax_base_cap_not_a_cash_discount() -> None:
    message = build_ev_tax_benefit_flex()
    body = message["contents"]["body"]["contents"]
    text = " ".join(item.get("text", "") for item in body)
    assert "2030/12/31" in text
    assert "完稅價格 140 萬元計算之稅額" in text
    assert message["contents"]["footer"]["contents"][0]["action"]["data"] == "action=ev_tax_more"
    assert "不是直接減免 140 萬元" in EV_TAX_BENEFIT_DETAIL
