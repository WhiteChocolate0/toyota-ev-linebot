FAQ_TEMPLATES: dict[str, str] = {
    "EV_BASIC": "EV 是以電池供電、由馬達驅動的車。要不要選它，通常要一起看日常里程、充電條件與長途使用方式。",
    "EV_VS_ICE": "電動車和油車沒有絕對哪台比較好；可從日常里程、補電方便度、長途習慣和持有成本一起比較。",
    "EV_VS_HEV": "電動車和油電車各有適合的生活情境；關鍵是固定充電條件、每日里程、長途頻率與成本偏好。",
    "EV_GENERAL_OPINION": "電車好不好，重點不只在車本身，而在你的充電條件與用車習慣。若日常補電方便，優勢會更明顯。",
    "ICE_FUTURE": "油車目前仍能正常使用與購買；真正需要一起看的，是未來政策、你預計持有多久，以及日常用車成本的變化。",
    "TOYOTA_BRAND": "評估 TOYOTA 品牌可拆成車型可靠度、保固、保養據點、售後與你家的實際使用需求，不必只用單一印象判斷。",
    "TOYOTA_EV": "TOYOTA 純電車可以從充電規格、官方保固、售後服務與你的日常補電條件一起確認。你想先看哪一項？",
    "BZ4X": "bZ4X 是否適合，要搭配日常里程、家中或工作地補電、長途頻率與成本條件一起看。",
    "BATTERY": "電池議題可分開看原廠保固、容量衰退、故障維修與安全使用；不要直接把它等同於一定要整顆更換。",
    "CHARGING": "充電便利性主要取決於固定車位、住宅補電條件，以及常用路線與工作地的充電安排。",
    "RANGE": "續航要搭配每日里程、長途頻率與沿途充電條件看，單看單一數字容易誤判。",
    "COST": "是否比較省，要把每月里程、能源價格、充電方式與持有年限一起看；可以再用成本試算把假設列清楚。",
    "MAINTENANCE": "保養可分為例行項目、耗材與高壓系統保障來看；比較時應以原廠保養資訊與實際使用情境為準。",
    "RESALE": "二手殘值受車況、市場、年份與供需影響很大，不適合當作保證值；比較時宜以區間與假設呈現。",
    "SAFETY": "安全問題建議從車輛碰撞防護、高壓系統設計、原廠指引與日常使用情境分開確認。",
    "POLICY": "汽車政策與補助會變動，適合以主管機關與原廠最新公告確認；也可先把它和你的預計持有年限一起評估。",
    "CALCULATOR": "可以，我會先比較兩台 TOYOTA 的長期用車能源成本，再依你的里程與持有年限列出假設。",
    "EV_FIT": "想知道生活是否適合 EV，可以先從日常里程、長途習慣與家庭補電條件做簡單健檢。",
    "UNKNOWN_RELEVANT": "這題跟 EV／TOYOTA 有關，我可以幫你一起拆解。你比較想知道的是車款、成本、使用方式，還是未來趨勢？",
}

FAQ_SOURCE_IDS: dict[str, str] = {
    "EV_BASIC": "src_ev_bev_definition",
    "EV_VS_ICE": "src_ev_is_better",
    "EV_VS_HEV": "src_bev_vs_hev",
    "EV_GENERAL_OPINION": "src_ev_is_better",
    "ICE_FUTURE": "src_tw_ice_existing_cars",
    "TOYOTA_BRAND": "src_toyota_brand_neutral",
    "TOYOTA_EV": "src_toyota_ev_lineup_tw",
    "BATTERY": "src_bz4x_battery_warranty",
    "SAFETY": "src_bz4x_battery_warranty",
    "CHARGING": "src_bz4x_charging",
    "RANGE": "src_faq_ev_range_anxiety",
    "COST": "src_faq_cost_ev_vs_hev",
    "MAINTENANCE": "src_faq_ev_maintenance",
    "POLICY": "src_tw_2040_new_car_electrification",
    "BZ4X": "src_bz4x_specs",
}


def source_id_for(topic: str, text: str) -> str | None:
    """Select the narrowest verified source without expanding the public taxonomy."""
    lowered = text.lower()
    is_bz4x = "bz4x" in lowered
    if topic == "BZ4X":
        if any(word in lowered for word in ("110v", "220v", "充電", "家裡", "家用", "充電樁")):
            return "src_faq_home_charging_needed"
        if any(word in lowered for word in ("ccs1", "j1772", "接頭", "規格")):
            return "src_bz4x_charge_connector"
        if any(word in lowered for word in ("743", "實際續航", "續航")):
            return "src_bz4x_range_realworld"
        if any(word in lowered for word in ("安全", "tss", "acc", "輔助")):
            return "src_bz4x_safety_tss"
        if any(word in lowered for word in ("保養", "半年", "10000")):
            return "src_bz4x_maintenance"
    if topic == "EV_BASIC":
        if any(word in lowered for word in ("phev", "插電油電")):
            return "src_phev_definition"
        if "油電" in text or "hybrid" in lowered or ("hev" in lowered and "phev" not in lowered):
            if any(word in text for word in ("動能回收", "煞車回收", "回充")):
                return "src_hev_regenerative_braking"
            return "src_hev_definition"
    if topic == "BATTERY" and ("油電" in text or "hybrid" in lowered or ("hev" in lowered and "phev" not in lowered)):
        return "src_hev_battery_warranty"
    if topic == "BATTERY" and any(word in text for word in ("8 年", "8年", "十六萬", "160,000", "160000")):
        return "src_faq_battery_8years"
    if topic == "CHARGING":
        if any(word in lowered for word in ("phev", "插電油電")):
            return "src_phev_home_charging"
        if "油電" in text or "hybrid" in lowered or ("hev" in lowered and "phev" not in lowered):
            return "src_hev_no_plug_charging"
        if any(word in lowered for word in ("110v", "220v", "家充", "家用", "家裡", "充電樁")):
            return "src_faq_home_charging_needed"
    if topic == "RANGE" and any(word in lowered for word in ("phev", "插電油電", "電池沒電")):
        return "src_phev_battery_empty"
    if topic == "SAFETY":
        return "src_bz4x_safety_tss"
    if topic == "TOYOTA_BRAND" and any(word in text for word in ("策略", "多元動力", "FCEV", "電動化")):
        return "src_toyota_electrified_strategy"
    if topic == "POLICY":
        if any(word in text for word in ("牌照稅", "使用牌照稅")):
            return "src_tw_ev_license_tax_exemption"
        if any(word in text for word in ("燃料費", "公路費", "公路使用養護")):
            return "src_tw_ev_road_fee_exemption"
    return FAQ_SOURCE_IDS.get(topic)
