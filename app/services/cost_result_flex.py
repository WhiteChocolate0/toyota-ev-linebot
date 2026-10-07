"""Conclusion-first LINE Flex formatter for energy-cost comparisons."""

import re


def build_cost_result_flex(result_text: str, calculation_id: str = "", source_type: str = "user") -> dict:
    """Present calculator output as conclusion → detail → assumptions.

    Arithmetic remains in CostFlowManager.  This formatter only gives the
    already calculated annual and cumulative differences an unambiguous visual
    hierarchy.
    """
    lines = [line.strip().lstrip("・") for line in result_text.splitlines() if line.strip()]
    title = next((line for line in lines if "能源成本比較" in line), "💰 能源成本比較")
    vehicle_names = [line for line in lines if line.startswith(("🌱", "⚡", "🔌", "⛽", "🛻", "🚗"))]
    pair = "  vs  ".join(_display_name(line) for line in vehicle_names[:2]) or "比較車款"
    annual_costs = [line for line in lines if "：約 NT$" in line and "／年" in line]
    annual_difference = next((line for line in lines if "每年約差" in line), "")
    total_difference = next((line for line in lines if "累積約差" in line), "")
    note = next((line for line in lines if line.startswith("※")), "※ 僅比較能源成本。")
    assumptions = [line for line in lines if any(key in line for key in ("年行駛", "充電假設", "油價", "PHEV 純電"))]

    cheaper = _cheaper_vehicle(annual_costs)
    annual_amount = _amount(annual_difference)
    conclusion = f"{cheaper} 每年約省" if cheaper else "每年約差"
    body: list[dict] = [
        {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#111827", "wrap": True},
        {"type": "text", "text": "根據目前輸入條件估算", "size": "xs", "color": "#6B7280", "margin": "sm"},
        {"type": "text", "text": pair, "weight": "bold", "size": "sm", "color": "#374151", "wrap": True, "margin": "lg"},
        {"type": "box", "layout": "vertical", "backgroundColor": "#ECFDF5", "cornerRadius": "12px", "paddingAll": "16px", "margin": "lg", "contents": [
            {"type": "text", "text": conclusion, "size": "sm", "color": "#047857", "weight": "bold"},
            {"type": "text", "text": annual_amount or "—", "size": "xxl", "weight": "bold", "color": "#065F46", "margin": "sm"},
            {"type": "text", "text": total_difference or "累積差額將依持有年限計算", "size": "xs", "color": "#047857", "wrap": True, "margin": "sm"},
        ]},
        _divider("xl"),
        {"type": "text", "text": "比較明細", "weight": "bold", "size": "md", "color": "#111827", "margin": "xl"},
    ]
    body.extend({"type": "text", "text": value, "size": "sm", "color": "#374151", "wrap": True, "margin": "md"} for value in annual_costs)
    if annual_difference:
        body += [_divider("xl"), {"type": "text", "text": annual_difference, "weight": "bold", "size": "md", "color": "#111827", "margin": "xl"}]
    if total_difference:
        body.append({"type": "text", "text": total_difference, "weight": "bold", "size": "md", "color": "#111827", "margin": "md"})
    if assumptions:
        body += [_divider("xl"), {"type": "text", "text": "計算假設", "weight": "bold", "size": "sm", "color": "#374151", "margin": "xl"}]
        body.extend({"type": "text", "text": f"• {value}", "size": "xs", "color": "#6B7280", "wrap": True, "margin": "sm"} for value in assumptions)
    body += [_divider("xl"), {"type": "text", "text": note, "size": "xxs", "color": "#9CA3AF", "wrap": True, "margin": "xl"}]
    share_button = (
        _button("產生分享卡", f"action=generate_share_card&calculation_id={calculation_id}", "link")
        if source_type == "group"
        else _button("分享結果", f"action=share_result&calculation_id={calculation_id}", "link")
    )
    return {"type": "flex", "altText": title, "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": body}, "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
        _button("換個情境看看", f"action=cost_sensitivity_menu&calculation_id={calculation_id}", "secondary"), _button("看完整成本", f"action=view_full_cost&calculation_id={calculation_id}", "secondary"), share_button, _button("返回功能選單", "action=show_service_menu", "secondary"),
    ]}}}


def build_full_cost_result_flex(result_text: str, calculation_id: str = "") -> dict:
    """Format the conversational full-TCO output without disguising assumptions as facts."""
    lines = [line.strip().lstrip("・") for line in result_text.splitlines() if line.strip()]
    title = next((line for line in lines if "完整持有成本比較" in line), "💰 完整持有成本比較")
    conclusion = next((line for line in lines if line.startswith("結論：")), "")
    totals = [line for line in lines if line.startswith(("bZ", "RAV", "COROLLA", "YAR", "ALTIS", "CAMRY", "CROWN", "HILUX", "LAND", "TOWN", "VIOS", "URBAN")) and "NT$" in line]
    assumptions = [line for line in lines if line.startswith(("假設：", "貸款", "未納入", "已依", "※"))]
    body: list[dict] = [
        {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#111827", "wrap": True},
        {"type": "text", "text": "依目前輸入條件的情境試算", "size": "xs", "color": "#6B7280", "margin": "sm"},
    ]
    if conclusion:
        body.append({"type": "box", "layout": "vertical", "backgroundColor": "#ECFDF5", "cornerRadius": "12px", "paddingAll": "16px", "margin": "lg", "contents": [{"type": "text", "text": conclusion, "weight": "bold", "size": "md", "color": "#065F46", "wrap": True}]})
    body += [_divider("xl"), {"type": "text", "text": "總成本與明細", "weight": "bold", "size": "md", "color": "#111827", "margin": "xl"}]
    body.extend({"type": "text", "text": line, "size": "sm", "color": "#374151", "wrap": True, "margin": "sm"} for line in lines if line.startswith(("・", "車價", "能源", "保養", "保險", "稅費", "輪胎", "停車", "雜支", "充電設備", "貸款", "殘值")) or line in totals)
    if assumptions:
        body += [_divider("xl"), {"type": "text", "text": "試算假設", "weight": "bold", "size": "sm", "color": "#374151", "margin": "xl"}]
        body.extend({"type": "text", "text": line, "size": "xxs", "color": "#6B7280", "wrap": True, "margin": "sm"} for line in assumptions)
    return {"type": "flex", "altText": title, "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": body}, "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
        _button("調整能源條件", f"action=edit_cost_inputs&calculation_id={calculation_id}", "secondary"), _button("返回能源成本", f"action=show_cost_result&calculation_id={calculation_id}", "secondary"), _button("返回功能選單", "action=show_service_menu", "secondary"),
    ]}}}


def build_share_card(result_text: str) -> dict:
    """Create a compact, non-sensitive Flex card suitable for forwarding.

    This intentionally omits loans and other personal financial inputs.  It is
    a LINE-native MVP share card; image rendering can be added without changing
    the result-action contract later.
    """
    lines = [line.strip().lstrip("・") for line in result_text.splitlines() if line.strip()]
    title = next((line for line in lines if "能源成本比較" in line), "💰 能源成本比較")
    vehicles = [line for line in lines if line.startswith(("🌱", "⚡", "🔌", "⛽", "🛻", "🚗"))]
    annual_costs = [line for line in lines if "：約 NT$" in line and "／年" in line]
    annual_difference = next((line for line in lines if "每年約差" in line), "")
    total_difference = next((line for line in lines if "累積約差" in line), "")
    assumptions = [line for line in lines if any(key in line for key in ("年行駛", "充電假設", "油價", "PHEV 純電"))]
    contents: list[dict] = [
        {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#111827", "wrap": True},
        {"type": "text", "text": "電車解惑所｜能源成本摘要", "size": "xs", "color": "#6B7280", "margin": "sm"},
        {"type": "text", "text": "  vs  ".join(_display_name(value) for value in vehicles[:2]) or "比較車款", "size": "sm", "weight": "bold", "color": "#374151", "wrap": True, "margin": "lg"},
        _divider("xl"),
    ]
    contents.extend({"type": "text", "text": value, "size": "sm", "color": "#374151", "wrap": True, "margin": "md"} for value in annual_costs)
    if annual_difference:
        contents.append({"type": "text", "text": annual_difference, "size": "lg", "weight": "bold", "color": "#065F46", "wrap": True, "margin": "xl"})
    if total_difference:
        contents.append({"type": "text", "text": total_difference, "size": "sm", "weight": "bold", "color": "#047857", "wrap": True, "margin": "sm"})
    if assumptions:
        contents += [_divider("xl"), {"type": "text", "text": "• " + "\n• ".join(assumptions[:3]), "size": "xxs", "color": "#6B7280", "wrap": True, "margin": "lg"}]
    contents.append({"type": "text", "text": "※ 僅比較能源成本", "size": "xxs", "color": "#9CA3AF", "margin": "lg"})
    return {"type": "flex", "altText": title, "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": contents}}}


def _divider(margin: str) -> dict:
    return {"type": "separator", "color": "#E5E7EB", "margin": margin}


def _button(label: str, data: str, style: str = "primary") -> dict:
    return {"type": "button", "style": style, "height": "sm", "action": {"type": "postback", "label": label, "data": data, "displayText": label}}


def _display_name(line: str) -> str:
    return line.split("\n", 1)[0]


def _amount(value: str) -> str:
    match = re.search(r"NT\$\s*[\d,]+", value)
    return match.group(0) if match else ""


def _cheaper_vehicle(costs: list[str]) -> str:
    parsed: list[tuple[str, int]] = []
    for cost in costs:
        amount = re.search(r"NT\$\s*([\d,]+)", cost)
        if amount:
            parsed.append((cost.split("：", 1)[0], int(amount.group(1).replace(",", ""))))
    return min(parsed, key=lambda item: item[1])[0] if len(parsed) >= 2 else ""
