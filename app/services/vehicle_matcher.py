import re


def normalize_vehicle_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def match_vehicle_name(text: str, profiles: list[dict]) -> dict | None:
    target = normalize_vehicle_name(text)
    if not target:
        return None
    for profile in profiles:
        candidates = [profile["model_name"], *profile.get("aliases", [])]
        if any(normalize_vehicle_name(candidate) == target for candidate in candidates):
            return profile
    return None


def match_vehicle_in_text(text: str, profiles: list[dict]) -> dict | None:
    """Find one catalogued model mentioned in a natural-language message.

    Exact input matching remains useful for form fields.  This companion helper
    is intentionally conservative for chat: short aliases such as ``CC`` must
    be standalone tokens so they do not accidentally match an unrelated word.
    """
    matches = find_vehicles_in_text(text, profiles)
    return matches[0] if matches else None


def find_vehicles_in_text(text: str, profiles: list[dict]) -> list[dict]:
    """Return each catalogued model mentioned in a message, in catalog order."""
    direct = match_vehicle_name(text, profiles)
    if direct:
        return [direct]

    lowered = text.lower()
    normalized_text = normalize_vehicle_name(text)
    matches: list[dict] = []
    seen_models: set[str] = set()
    for profile in profiles:
        candidates = [profile["model_name"], *profile.get("aliases", [])]
        for candidate in candidates:
            normalized_candidate = normalize_vehicle_name(candidate)
            if not normalized_candidate:
                continue
            if len(normalized_candidate) <= 2:
                if re.search(rf"(?<![a-z0-9]){re.escape(normalized_candidate)}(?![a-z0-9])", lowered):
                    break
            elif normalized_candidate in normalized_text:
                break
        else:
            continue
        model_name = profile["model_name"]
        if model_name not in seen_models:
            matches.append(profile)
            seen_models.add(model_name)
    return matches


def is_explicit_vehicle_comparison(text: str) -> bool:
    """Whether a group message clearly asks to compare vehicles.

    Group messages should not trigger a reply merely for mentioning a model.
    """
    lowered = text.lower()
    strong_markers = ("比較", "比一下", "幫我比", "對比", "相較", "差異", "差在哪", "怎麼選", "哪台", "這幾台", "vs", "v.s.")
    if any(marker in lowered for marker in strong_markers):
        return True
    # 「我跟家人開 RAV4」不是比較；「RAV4 跟 bZ4X」才是。
    if "跟" in lowered and any(marker in lowered for marker in ("bz4x", "電動車", "油電", "hybrid", "哪個")):
        return True
    return "還是" in lowered and any(marker in lowered for marker in ("電動車", "油電", "hybrid", "bz4x"))


def vehicle_conversation_reply(profiles: list[dict], source_type: str) -> str:
    """Create an invitation from structured vehicle context, never duplicate a model."""
    model_names = list(dict.fromkeys(profile["model_name"] for profile in profiles))
    if not model_names:
        return "要不要我陪你從日常用車、充電便利性和成本一起看看？"
    model_label = " 跟 ".join(model_names)
    is_comparison = len(model_names) >= 2
    if source_type == "group":
        if not is_comparison:
            return (
                f"你們正在聊 {model_label} 的使用情境嗎？"
                "要不要我先從日常里程和充電條件，陪大家一起整理看看？"
            )
        return (
            f"你們正在聊 {model_label} 嗎？"
            "要不要我用日常里程、充電條件和 8 年能源成本，陪你們一起比較看看？"
        )
    if not is_comparison and model_names[0].lower() == "bz4x":
        return (
            "正在看 bZ4X 嗎？"
            "想先從日常用車、充電便利性，還是成本開始一起聊？"
        )
    if is_comparison:
        return (
            f"正在比較 {model_label} 嗎？"
            "我可以從日常用車、充電便利性和成本陪你一起慢慢看。"
        )
    return (
        f"正在看 {model_label} 嗎？"
        "如果你想和 bZ4X 比較，我可以從日常用車、充電便利性和成本陪你一起慢慢看。"
    )
