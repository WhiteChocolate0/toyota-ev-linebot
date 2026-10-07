"""LINE Flex content for evidence-bounded EV advantages."""


def build_ev_tax_benefit_flex() -> dict:
    return {
        "type": "flex", "altText": "純電車貨物稅優惠（至 2030/12/31）",
        "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": "💰 貨物稅優惠", "weight": "bold", "size": "lg"},
            {"type": "text", "text": "純電車完成登記，可享貨物稅免徵優惠至 2030/12/31。", "wrap": True, "margin": "md"},
            {"type": "text", "text": "電動小客車免徵額以完稅價格 140 萬元計算之稅額為限。", "wrap": True, "size": "sm", "color": "#4B5563", "margin": "md"},
        ]}, "footer": {"type": "box", "layout": "vertical", "contents": [
            {"type": "button", "style": "primary", "action": {"type": "postback", "label": "了解更多", "data": "action=ev_tax_more"}}
        ]}},
    }


EV_TAX_BENEFIT_DETAIL = (
    "💰 純電車貨物稅優惠\n\n"
    "依《貨物稅條例》第 12 條之 3，自 2017/1/28 至 2030/12/31，購買完全以電能為動力的電動車輛並完成新領牌照登記者，可免徵其應徵貨物稅。\n\n"
    "但電動小客車的免徵金額，以完稅價格新臺幣 140 萬元計算的稅額為限；超過部分不予免徵。140 萬元是完稅價格的計算基準上限，並不是直接減免 140 萬元。\n\n"
    "資料來源｜財政部稅務入口網\n"
    "https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-saving-manual/national/commodity-tax/0kPmZDo"
)
