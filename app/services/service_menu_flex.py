"""Persistent, reusable entry points for the LINE group experience."""


_ENTRIES = (
    ("我適合開電動車嗎？", "看看你的里程、充電與長途習慣。", "開始評估", "start_ev_fit"),
    ("電車真的比較省嗎？", "比較油車、油電與 EV 的長期成本。", "比較成本", "start_cost_compare"),
    ("哪台車比較適合我？", "從空間、預算與使用需求幫你篩。", "幫我選車", "start_vehicle_recommendation"),
    ("我有電車問題", "直接問電池、充電、續航或 TOYOTA。", "我要提問", "open_ev_question_help"),
)

_PRIVATE_ENTRIES = (
    ("我適合開電動車嗎？", "看看你的里程、充電與長途習慣。", "開始評估", "start_ev_fit"),
    ("幫我選車", "依預算、空間與使用需求幫你篩。", "幫我選車", "start_vehicle_recommendation"),
    ("比較車款與成本", "一次比較車價、空間、能源與長期成本。", "開始比較", "start_vehicle_comparison"),
    ("我有電車問題", "直接問電池、充電、續航或 TOYOTA。", "我要提問", "open_ev_question_help"),
    ("查看上次結果", "回到最近的評估、比較或試算。", "查看結果", "view_recent_results"),
    ("邀請我進家庭群組", "和家人一起討論、整理疑慮。", "查看邀請方式", "invite_to_family_group"),
)


def build_service_menu_flex() -> dict:
    """A history-safe menu: every action derives its owner from the postback source."""
    return {
        "type": "flex", "altText": "電車解惑所功能選單",
        "contents": {"type": "carousel", "contents": [_entry_bubble(*entry) for entry in _ENTRIES]},
    }


def build_private_service_menu() -> dict:
    return {"type": "flex", "altText": "個人探索功能選單", "contents": {"type": "carousel", "contents": [_entry_bubble(*entry) for entry in _PRIVATE_ENTRIES]}}


def build_group_service_menu() -> dict:
    return build_service_menu_flex()


def build_first_use_menu_flex() -> dict:
    """Compact first-use follow-up; it complements rather than replaces an answer."""
    choices = _ENTRIES[:3]
    return {
        "type": "flex", "altText": "第一次使用的功能入口",
        "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
            {"type": "text", "text": "第一次使用嗎？", "weight": "bold", "size": "lg", "color": "#111827"},
            {"type": "text", "text": "我還可以幫你從生活條件、成本或選車開始。", "size": "sm", "color": "#374151", "wrap": True, "margin": "md"},
        ]}, "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
            _button(label, action) for _title, _description, label, action in choices
        ]}},
    }


def _entry_bubble(title: str, description: str, label: str, action: str) -> dict:
    return {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
        {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#111827", "wrap": True},
        {"type": "text", "text": description, "size": "sm", "color": "#374151", "wrap": True, "margin": "lg"},
    ]}, "footer": {"type": "box", "layout": "vertical", "contents": [_button(label, action)]}}


def _button(label: str, action: str) -> dict:
    return {"type": "button", "style": "primary", "height": "sm", "action": {
        "type": "postback", "label": label, "data": f"action={action}", "displayText": label,
    }}
