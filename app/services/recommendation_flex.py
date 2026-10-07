from app.services.recommendation_engine import Candidate


def build_recommendation_flex(candidates: list[Candidate]) -> dict:
    bubbles = []
    for candidate in candidates:
        vehicle = candidate.vehicle
        contents = [{"type": "text", "text": str(vehicle["model_name"]), "weight": "bold", "size": "xl", "wrap": True},
                    {"type": "text", "text": "適合你的地方", "weight": "bold", "size": "sm", "margin": "lg"}]
        contents += [{"type": "text", "text": f"• {reason}", "size": "xs", "wrap": True, "margin": "sm"} for reason in candidate.reasons]
        if candidate.cautions:
            contents += [{"type": "text", "text": "需要注意", "weight": "bold", "size": "sm", "margin": "lg"}]
            contents += [{"type": "text", "text": f"• {note}", "size": "xs", "wrap": True, "margin": "sm"} for note in candidate.cautions]
        data = f"action=add_candidate_to_cost&vehicle_id={vehicle['id']}"
        bubbles.append({"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": contents}, "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
            {"type": "button", "style": "primary", "action": {"type": "postback", "label": "加入成本比較", "data": data}},
            {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "返回功能選單", "data": "action=show_service_menu"}},
        ]}})
    return {"type": "flex", "altText": "依你的需求可進一步比較的車款", "contents": {"type": "carousel", "contents": bubbles}}
