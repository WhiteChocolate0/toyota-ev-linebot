"""Conclusion-first Flex card for the EV lifestyle suitability check."""


def build_ev_fit_flex(result_text: str) -> dict:
    lines = [line.strip() for line in result_text.splitlines() if line.strip()]
    title = lines[0] if lines else "我適合開電動車嗎？"
    summary = next((line for line in lines if line.startswith(("整體來看", "你的日常", "目前最大的"))), "請確認目前的用車條件。")
    statuses = [line for line in lines if line.startswith(("✅", "🟡", "⚠️", "❗", "◻️"))]
    blocker = next((line for line in lines if line.startswith("最需要確認：")), "最需要確認：日常充電條件")
    next_step = next((line for line in lines if line.startswith("下一步：")), "下一步：比較長期用車成本。")
    contents: list[dict] = [
        {"type": "text", "text": title, "size": "xl", "weight": "bold", "color": "#111827", "wrap": True},
        {"type": "text", "text": summary, "size": "sm", "color": "#374151", "wrap": True, "margin": "lg"},
        {"type": "separator", "margin": "xl", "color": "#E5E7EB"},
    ]
    for status in statuses:
        color = "#15803D" if status.startswith("✅") else "#B45309" if status.startswith(("🟡", "⚠️")) else "#B91C1C" if status.startswith("❗") else "#4B5563"
        contents.append({"type": "text", "text": status, "size": "sm", "weight": "bold", "color": color, "wrap": True, "margin": "lg"})
    contents += [
        {"type": "separator", "margin": "xl", "color": "#E5E7EB"},
        {"type": "text", "text": blocker, "size": "sm", "weight": "bold", "color": "#111827", "wrap": True, "margin": "xl"},
        {"type": "text", "text": next_step, "size": "sm", "color": "#374151", "wrap": True, "margin": "md"},
    ]
    feature_index = next((index for index, line in enumerate(lines) if line.startswith("💡 bZ4X 補電彈性")), None)
    if feature_index is not None:
        feature_text = lines[feature_index + 1] if feature_index + 1 < len(lines) else ""
        contents += [
            {"type": "separator", "margin": "xl", "color": "#E5E7EB"},
            {"type": "text", "text": "💡 bZ4X 補電彈性", "size": "sm", "weight": "bold", "color": "#1D4ED8", "wrap": True, "margin": "xl"},
            {"type": "text", "text": feature_text, "size": "xs", "color": "#374151", "wrap": True, "margin": "sm"},
        ]
    contents.append({"type": "text", "text": "※ 本結果僅依目前生活條件整理，不構成購車建議。", "size": "xxs", "color": "#9CA3AF", "wrap": True, "margin": "xl"})
    return {"type": "flex", "altText": title, "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": contents}, "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
        {"type": "button", "style": "primary", "height": "sm", "action": {"type": "postback", "label": "比較用車成本", "data": "action=start_cost_compare", "displayText": "比較用車成本"}},
        {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "postback", "label": "幫我選車", "data": "action=start_vehicle_recommendation", "displayText": "幫我選車"}},
        {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "postback", "label": "返回功能選單", "data": "action=show_service_menu", "displayText": "返回功能選單"}},
    ]}}}
