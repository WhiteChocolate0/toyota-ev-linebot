from app.services.cost_flow import cost_flow_manager
from app.services.conversation_context import conversation_context_manager
from app.services.event_processor import EventProcessor, append_official_source, flow_scope


class FakeLineClient:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.loading_chats: list[tuple[str, int]] = []
    def reply_group_welcome(self, reply_token: str) -> None:
        self.replies.append("welcome")
    def reply_text(self, reply_token: str, text: str) -> None:
        self.replies.append(text)
    def reply_texts(self, reply_token: str, texts: list[str]) -> None:
        self.replies.extend(texts)
    def show_loading_animation(self, user_id: str, seconds: int = 5) -> None:
        self.loading_chats.append((user_id, seconds))


class FakeRepository:
    def claim_event(self, event_id: str) -> bool:
        return True
    def touch_group(self, line_group_id: str) -> str:
        return "group-db-id"
    def record_concern(self, group_id: str, concern_type: str) -> None:
        pass
    def get_knowledge_source(self, source_id: str) -> dict:
        return {"title": "官方測試來源", "url": "https://example.com/source"}
    def list_active_vehicle_profiles(self) -> list[dict]:
        return [
            {"model_name": "RAV4", "model_year": 2025, "trim_name": None, "drivetrain": "gasoline", "aliases": ["rav 4"]},
            {"model_name": "bZ4X", "model_year": 2025, "trim_name": None, "drivetrain": "ev", "aliases": ["bz4x"]},
        ]
    def get_vehicle_feature(self, model_name: str, feature_code: str) -> dict | None:
        if (model_name, feature_code) == ("bZ4X", "HOME_110V_CHARGING"):
            return {"description": "bZ4X 隨車附原廠 AC 充電線，可連接一般家用 110V 插座充電"}
        return None


class FakeRewriter:
    is_enabled = True

    def rewrite_vehicle_reply(self, *, fallback: str, **kwargs: object) -> str:
        return fallback


def test_source_is_appended_to_supported_concern_reply() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "event-source", "type": "message", "replyToken": "reply", "source": {"type": "group", "groupId": "group"}, "message": {"type": "text", "text": "電池可以用多久"}}])
    assert "官方來源｜官方測試來源" in client.replies[0]


def test_faq_cites_verified_knowledge_without_pasting_source_content() -> None:
    class KnowledgeRepository(FakeRepository):
        def get_knowledge_source(self, source_id: str) -> dict:
            assert source_id == "src_tw_ice_existing_cars"
            return {
                "title": "油車未來還能不能繼續開", "url": "https://example.com/official",
                "content": "既有燃油車是否可繼續使用，仍依當時有效法規管理。",
            }
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=KnowledgeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "event-knowledge-content", "type": "message", "replyToken": "reply", "source": {"type": "group", "groupId": "group"}, "message": {"type": "text", "text": "油車還能開"}}])
    assert client.replies[0].startswith("油車目前仍能正常使用")
    assert "仍依當時有效法規管理" not in client.replies[0]
    assert "官方來源｜油車未來還能不能繼續開" in client.replies[0]


def test_no_source_keeps_short_reply_usable() -> None:
    assert append_official_source("短答", None) == "短答"


def test_HANDOFF_BOT_001_private_valid_token_imports_normalized_short_lived_context() -> None:
    raw_token = "A" * 43
    class CampaignRepository(FakeRepository):
        def consume_campaign_token(self, token: str, user_id: str) -> dict:
            assert token == raw_token and user_id == "campaign-user"
            return {"status": "SUCCESS", "quiz_result_id": "result-1", "persona_key": "money", "ability_scores": {"money": 8}, "result_summary": {"persona_name": "省錢規劃型", "conversation_hint": "先從家庭成本討論開始"}}

        def save_conversation_context(self, *_args) -> bool:
            return True

    client = FakeLineClient()
    source = {"type": "user", "userId": "campaign-user"}
    processor = EventProcessor(line_client=client, repository=CampaignRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "campaign-event", "type": "postback", "replyToken": "reply", "source": source, "postback": {"data": f"campaign_token={raw_token}"}}])
    context = conversation_context_manager.get(flow_scope(source))
    assert context and context.slots["campaign_quiz_result_id"] == "result-1"
    assert context.slots["campaign_summary"] == {"persona_name": "省錢規劃型", "conversation_hint": "先從家庭成本討論開始"}
    assert context.slots["campaign_ability_scores"] == {"money": 8}
    assert raw_token not in str(context.slots)
    assert "token_hash" not in str(context.slots)
    assert "只會作為這次對話的提示" in client.replies[0]


def test_GROUP_HANDOFF_001_group_campaign_postback_does_not_consume_token() -> None:
    raw_token = "B" * 43
    class NoConsumeRepository(FakeRepository):
        consume_calls = 0
        def consume_campaign_token(self, *_args):
            self.consume_calls += 1
            raise AssertionError("group source must not call the consume RPC")
    repository = NoConsumeRepository()
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=repository, rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "group-campaign-event", "type": "postback", "replyToken": "reply", "source": {"type": "group", "groupId": "group", "userId": "member"}, "postback": {"data": f"campaign_token={raw_token}"}}])
    assert repository.consume_calls == 0
    assert "1 對 1 聊天" in client.replies[0]
    assert raw_token not in client.replies[0]


def test_group_campaign_text_does_not_consume_token() -> None:
    raw_token = "C" * 43
    class NoConsumeRepository(FakeRepository):
        def consume_campaign_token(self, *_args):
            raise AssertionError("group source must not call the consume RPC")
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=NoConsumeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "group-campaign-text", "type": "message", "replyToken": "reply", "source": {"type": "room", "roomId": "room", "userId": "member"}, "message": {"type": "text", "text": f"campaign_token={raw_token}"}}])
    assert "1 對 1 聊天" in client.replies[0]
    assert raw_token not in client.replies[0]


def test_HANDOFF_BOT_007_private_campaign_text_uses_canonical_result_id() -> None:
    raw_token = "D" * 43
    class CampaignRepository(FakeRepository):
        def consume_campaign_token(self, token: str, _user_id: str) -> dict:
            assert token == raw_token
            return {"status": "SUCCESS", "quiz_result_id": "result-text", "persona_key": "safety", "result_summary": {}}
        def save_conversation_context(self, *_args) -> bool:
            return True
    client = FakeLineClient()
    source = {"type": "user", "userId": "campaign-text-user"}
    processor = EventProcessor(line_client=client, repository=CampaignRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "private-campaign-text", "type": "message", "replyToken": "reply", "source": source, "message": {"type": "text", "text": f"campaign_token={raw_token}"}}])
    context = conversation_context_manager.get(flow_scope(source))
    assert context and context.slots["campaign_quiz_result_id"] == "result-text"
    assert raw_token not in str(context.slots)


def test_HANDOFF_BOT_003_to_006_failure_contract_has_friendly_user_copy() -> None:
    cases = [
        ("TOKEN_EXPIRED", "這份活動結果連結已失效，可以重新完成挑戰後再帶結果過來。"),
        ("TOKEN_NOT_FOUND", "這個活動結果連結無法使用"),
        ("RESULT_NOT_FOUND", "目前找不到這份活動結果"),
        ("TOKEN_ALREADY_CONSUMED", "請回到活動網站重新產生接續連結"),
    ]
    for index, (status, expected) in enumerate(cases):
        class ErrorRepository(FakeRepository):
            def consume_campaign_token(self, *_args):
                return {"status": status, "quiz_result_id": "different-result"}
        client = FakeLineClient()
        processor = EventProcessor(line_client=client, repository=ErrorRepository(), rewriter=FakeRewriter())
        processor.process([{"webhookEventId": f"campaign-error-{index}", "type": "postback", "replyToken": "reply", "source": {"type": "user", "userId": f"campaign-error-user-{index}"}, "postback": {"data": f"campaign_token={'E' * 43}"}}])
        assert expected in client.replies[0]
        assert all(code not in client.replies[0] for code in ("TOKEN_NOT_FOUND", "invalid", "database error"))


def test_HANDOFF_BOT_004_consumed_token_for_same_context_gets_already_imported_copy() -> None:
    class ConsumedRepository(FakeRepository):
        def consume_campaign_token(self, *_args):
            return {"status": "TOKEN_ALREADY_CONSUMED", "quiz_result_id": "result-same"}
        def save_conversation_context(self, *_args) -> bool:
            return True
    client = FakeLineClient()
    source = {"type": "user", "userId": "consumed-user"}
    scope = flow_scope(source)
    conversation_context_manager.update(scope, topic="CAMPAIGN_HANDOFF", goal="LEARN", slots={"campaign_quiz_result_id": "result-same"}, intent="CAMPAIGN_HANDOFF")
    processor = EventProcessor(line_client=client, repository=ConsumedRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "campaign-consumed-same", "type": "postback", "replyToken": "reply", "source": source, "postback": {"data": f"campaign_token={'F' * 43}"}}])
    assert "已經帶進來" in client.replies[0]


def test_HANDOFF_BOT_008_context_never_persists_raw_token() -> None:
    raw_token = "G" * 43
    class CampaignRepository(FakeRepository):
        def consume_campaign_token(self, *_args):
            return {"status": "SUCCESS", "quiz_result_id": "result-private", "persona_key": "face", "ability_scores": {"face": 7}, "result_summary": {"profile": {"name": "比較型", "communicationTip": "先談需求"}, "extra": "must-not-persist"}}
        def save_conversation_context(self, *_args) -> bool:
            return True
    client = FakeLineClient()
    source = {"type": "user", "userId": "minimal-context-user"}
    processor = EventProcessor(line_client=client, repository=CampaignRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "campaign-context-minimal", "type": "postback", "replyToken": "reply", "source": source, "postback": {"data": f"campaign_token={raw_token}"}}])
    context = conversation_context_manager.get(flow_scope(source))
    assert context
    assert raw_token not in str(context.slots)
    assert "token_hash" not in str(context.slots)
    assert "extra" not in str(context.slots)
    assert context.slots["campaign_ability_scores"] == {"face": 7}


def test_HANDOFF_BOT_009_handoff_repository_path_never_queries_quiz_answers() -> None:
    from app.services.linebot_repository import LinebotRepository
    from types import SimpleNamespace
    class RPC:
        def __init__(self): self.tables = []
        def rpc(self, name, params):
            self.tables.append((name, params))
            return self
        def execute(self): return SimpleNamespace(data={"status": "invalid"})
        def table(self, name):
            self.tables.append(name)
            raise AssertionError("handoff must not query tables")
    rpc = RPC()
    repository = LinebotRepository.__new__(LinebotRepository)
    repository._client = SimpleNamespace(_client=rpc)
    assert repository.consume_campaign_token("H" * 43)["status"] == "TOKEN_NOT_FOUND"
    assert len(rpc.tables) == 1 and rpc.tables[0][0] == "consume_campaign_handoff"


def test_unspecified_cost_calculation_period_defaults_to_five_years() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "event-default-period", "type": "message", "replyToken": "reply", "source": {"type": "user", "userId": "period-user"}, "message": {"type": "text", "text": "成本試算"}}])
    assert client.replies[0].startswith("💰 成本試算")


def test_cost_calculator_command_restarts_an_unfinished_direct_flow() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    first = {"webhookEventId": "event-restart-first", "type": "message", "replyToken": "reply-1", "source": {"type": "user", "userId": "restart-user"}, "message": {"type": "text", "text": "成本試算"}}
    processor.process([first])
    second = {"webhookEventId": "event-restart-second", "type": "message", "replyToken": "reply-2", "source": {"type": "user", "userId": "restart-user"}, "message": {"type": "text", "text": "成本試算"}}
    processor.process([second])
    assert len(client.replies) == 2
    assert client.replies[-1].startswith("💰 成本試算")


def test_cancelled_private_cost_flow_does_not_capture_the_next_faq() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    source = {"type": "user", "userId": "cancel-private-user"}
    processor.process([{"webhookEventId": "cancel-start", "type": "message", "replyToken": "one", "source": source, "message": {"type": "text", "text": "成本試算"}}])
    scope = flow_scope(source)
    assert cost_flow_manager.is_active(scope)
    processor.process([{"webhookEventId": "cancel-now", "type": "message", "replyToken": "two", "source": source, "message": {"type": "text", "text": "取消"}}])
    assert not cost_flow_manager.is_active(scope)
    processor.process([{"webhookEventId": "cancel-faq", "type": "message", "replyToken": "three", "source": source, "message": {"type": "text", "text": "電池可以用多久？"}}])
    assert "官方來源" in client.replies[-1]


def test_text_and_postback_cancel_use_persisted_flow_cancellation() -> None:
    class CancellationRepository(FakeRepository):
        def __init__(self) -> None: self.calls: list[tuple] = []
        def cancel_active_conversation_flows(self, group_id, user_id) -> bool:
            self.calls.append(("flows", group_id, user_id)); return True
        def cancel_vehicle_comparison_session(self, group_id, user_id) -> bool:
            self.calls.append(("comparison", group_id, user_id)); return True
    repository = CancellationRepository(); client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=repository, rewriter=FakeRewriter())
    source = {"type": "user", "userId": "persisted-cancel-user"}
    processor.process([{"webhookEventId": "cancel-text", "type": "message", "replyToken": "one", "source": source, "message": {"type": "text", "text": "取消"}}])
    processor.process([{"webhookEventId": "cancel-button", "type": "postback", "replyToken": "two", "source": source, "postback": {"data": "action=cancel_flow&flow_id=COST_CALCULATION"}}])
    assert repository.calls == [
        ("flows", None, "persisted-cancel-user"), ("comparison", None, "persisted-cancel-user"),
        ("flows", None, "persisted-cancel-user"), ("comparison", None, "persisted-cancel-user"),
    ]


class PriceRepository(FakeRepository):
    def __init__(self, profiles: list[dict] | None = None) -> None:
        self.context_rows: dict[tuple[str | None, str], dict] = {}
        self._profiles = profiles or [{"id": "bz4x-id", "model_name": "bZ4X", "model_year": 2025, "trim_name": None, "drivetrain": "ev", "aliases": ["bz4x"], "purchase_price_ntd": 1_280_000, "source_url": "https://example.com/bz4x"}]
    def list_active_vehicle_profiles(self) -> list[dict]: return self._profiles
    def get_conversation_context(self, group_id, user_id): return self.context_rows.get((group_id, user_id))
    def save_conversation_context(self, group_id, user_id, context, expires_at) -> bool:
        self.context_rows[(group_id, user_id)] = {"context_json": context, "expires_at": expires_at}
        return True


def _private_event(event_id: str, user_id: str, text: str) -> dict:
    return {"webhookEventId": event_id, "type": "message", "replyToken": event_id, "source": {"type": "user", "userId": user_id}, "message": {"type": "text", "text": text}}


def test_vehicle_name_sets_active_vehicle_and_price_followup_uses_it() -> None:
    repository = PriceRepository(); client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=repository, rewriter=FakeRewriter())
    processor.process([_private_event("price-name", "price-user", "bZ4X")])
    scope = flow_scope({"type": "user", "userId": "price-user"})
    assert conversation_context_manager.get(scope).active_vehicle_id == "bz4x-id"
    processor.process([_private_event("price-followup", "price-user", "多少錢")])
    assert "NT$ 1,280,000" in client.replies[-1]
    assert "持有年限" not in client.replies[-1]


def test_price_followup_survives_cold_start_and_price_without_vehicle_requests_model() -> None:
    repository = PriceRepository(); client = FakeLineClient()
    first = EventProcessor(line_client=client, repository=repository, rewriter=FakeRewriter())
    first.process([_private_event("cold-price-name", "cold-price-user", "bZ4X")])
    scope = flow_scope({"type": "user", "userId": "cold-price-user"})
    conversation_context_manager.clear(scope)  # simulate a fresh Vercel instance
    second = EventProcessor(line_client=client, repository=repository, rewriter=FakeRewriter())
    second.process([_private_event("cold-price-followup", "cold-price-user", "車價多少")])
    assert "NT$ 1,280,000" in client.replies[-1]
    second.process([_private_event("price-no-vehicle", "no-price-user", "多少錢")])
    assert client.replies[-1] == "你想問哪一台車的價格？可以直接告訴我車名。"


def test_vehicle_price_is_not_routed_to_ownership_cost_and_cost_still_is() -> None:
    repository = PriceRepository(); client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=repository, rewriter=FakeRewriter())
    processor.process([_private_event("price-explicit", "explicit-price-user", "bZ4X 車價多少")])
    assert "NT$ 1,280,000" in client.replies[-1]
    processor.process([_private_event("ownership-explicit", "ownership-user", "bZ4X 一年養車多少")])
    assert "持有年限" in client.replies[-1]


def test_multi_powertrain_price_requires_disambiguation() -> None:
    profiles = [
        {"id": "cc-gas", "model_name": "COROLLA CROSS", "model_year": 2025, "trim_name": "汽油", "drivetrain": "gasoline", "aliases": ["corolla cross"], "purchase_price_ntd": 800_000},
        {"id": "cc-hev", "model_name": "COROLLA CROSS", "model_year": 2025, "trim_name": "Hybrid", "drivetrain": "hybrid", "aliases": ["corolla cross hybrid"], "purchase_price_ntd": 900_000},
    ]
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=PriceRepository(profiles), rewriter=FakeRewriter())
    processor.process([_private_event("price-cc", "cc-user", "Corolla Cross 多少錢？")])
    assert "不同動力或車型" in client.replies[-1]


def test_direct_message_confirms_catalogued_vehicle() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "event-vehicle-direct", "type": "message", "replyToken": "reply", "source": {"type": "user", "userId": "user"}, "message": {"type": "text", "text": "我目前開 RAV4"}}])
    assert client.replies[0] == "正在看 RAV4 嗎？如果你想和 bZ4X 比較，我可以從日常用車、充電便利性和成本陪你一起慢慢看。"
    assert client.loading_chats == [("user", 5)]


def test_group_vehicle_mention_is_quiet_without_a_comparison_question() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "event-vehicle-group-quiet", "type": "message", "replyToken": "reply", "source": {"type": "group", "groupId": "group"}, "message": {"type": "text", "text": "我家的是 RAV4"}}])
    assert client.replies == []


def test_group_vehicle_comparison_receives_a_confirmation() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "event-vehicle-group-compare", "type": "message", "replyToken": "reply", "source": {"type": "group", "groupId": "group"}, "message": {"type": "text", "text": "RAV4 跟 bZ4X 怎麼比較？"}}])
    assert "【你現在比較的 2 台】" in client.replies[0]
    assert "RAV4" in client.replies[0] and "bZ4X" in client.replies[0]
    assert client.loading_chats == []

    processor.process([{"webhookEventId": "event-vehicle-group-accept", "type": "message", "replyToken": "reply-2", "source": {"type": "group", "groupId": "group"}, "message": {"type": "text", "text": "好呀"}}])
    assert "目前支援" in client.replies[1]


def test_bz4x_is_not_repeated_when_it_is_the_only_mentioned_model() -> None:
    client = FakeLineClient()
    processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    processor.process([{"webhookEventId": "event-bz4x-direct", "type": "message", "replyToken": "reply", "source": {"type": "user", "userId": "bz-user"}, "message": {"type": "text", "text": "我想了解 bZ4X"}}])
    assert client.replies[0] == "正在看 bZ4X 嗎？想先從日常用車、充電便利性，還是成本開始一起聊？"


def _group_message(event_id: str, user_id: str, text: str) -> dict:
    return {"webhookEventId": event_id, "type": "message", "replyToken": event_id, "source": {"type": "group", "groupId": "ownership-group", "userId": user_id}, "message": {"type": "text", "text": text}}


def test_group_member_chat_cannot_pollute_another_members_pending_flow() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    owner = _group_message("owner-start", "U123", "成本試算")
    processor.process([owner])
    owner_scope = flow_scope(owner["source"])
    assert cost_flow_manager.current_stage(owner_scope) == "vehicle_type"
    processor.process([_group_message("other-chat", "U456", "晚餐吃什麼")])
    assert cost_flow_manager.current_stage(owner_scope) == "vehicle_type"
    assert len(client.replies) == 1


def test_group_faq_does_not_interrupt_another_members_cost_flow() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    owner = _group_message("owner-faq-start", "U123", "成本試算")
    processor.process([owner]); owner_scope = flow_scope(owner["source"])
    processor.process([_group_message("other-faq", "U456", "@電車解惑所 電池可以用多久？")])
    assert cost_flow_manager.current_stage(owner_scope) == "vehicle_type"
    assert any("官方來源" in reply for reply in client.replies)


def test_general_relevant_faq_does_not_interrupt_another_members_cost_flow() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    owner = _group_message("owner-brand-start", "U123", "成本試算")
    processor.process([owner]); owner_scope = flow_scope(owner["source"])
    processor.process([_group_message("other-brand-faq", "U456", "Toyota 品牌可靠嗎？")])
    assert cost_flow_manager.current_stage(owner_scope) == "vehicle_type"
    assert any("TOYOTA 品牌" in reply for reply in client.replies)


def test_group_advantage_question_does_not_become_a_cost_flow_value() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    owner = _group_message("owner-advantage-start", "U123", "成本試算")
    processor.process([owner]); owner_scope = flow_scope(owner["source"])
    processor.process([_group_message("owner-advantage-question", "U123", "Toyota 電車有什麼優勢")])
    assert cost_flow_manager.current_stage(owner_scope) == "vehicle_type"
    assert any("充電規格" in reply for reply in client.replies)


def test_vehicle_space_need_does_not_become_a_cost_flow_value() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    owner = _group_message("owner-space-start", "U123", "成本試算")
    processor.process([owner]); owner_scope = flow_scope(owner["source"])
    processor.process([_group_message("owner-space-need", "U123", "我想要後車廂大一點")])
    assert cost_flow_manager.current_stage(owner_scope) == "vehicle_type"
    assert "空間需求" in client.replies[-1]


def test_group_postback_from_non_owner_does_not_change_owner_flow() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    owner = _group_message("owner-postback-start", "U123", "成本試算")
    processor.process([owner]); owner_scope = flow_scope(owner["source"])
    event = {"webhookEventId": "other-years", "type": "postback", "replyToken": "other-years", "source": {"type": "group", "groupId": "ownership-group", "userId": "U456"}, "postback": {"data": "years=5"}}
    processor.process([event])
    assert cost_flow_manager.current_stage(owner_scope) == "vehicle_type"
    assert "另一位成員操作中" in client.replies[-1]


def test_two_group_members_can_start_independent_cost_flows() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    first = _group_message("multi-owner", "U123", "成本試算")
    second = _group_message("multi-other", "U456", "成本試算")
    processor.process([first, second])
    assert flow_scope(first["source"]) != flow_scope(second["source"])
    assert cost_flow_manager.is_active(flow_scope(first["source"]))
    assert cost_flow_manager.is_active(flow_scope(second["source"]))


def test_ev_fit_starts_and_completes_from_group_quick_reply_answers() -> None:
    client = FakeLineClient(); processor = EventProcessor(line_client=client, repository=FakeRepository(), rewriter=FakeRewriter())
    source = {"type": "group", "groupId": "fit-group", "userId": "U123"}
    processor.process([{"webhookEventId": "fit-start", "type": "message", "replyToken": "fit-start", "source": source, "message": {"type": "text", "text": "我適合開電動車嗎？"}}])
    for index, answer in enumerate(("20_40", "monthly", "accept", "yes", "HOME_110V", "HOME_CHARGE_DONE", "no")):
        processor.process([{"webhookEventId": f"fit-{index}", "type": "postback", "replyToken": f"fit-{index}", "source": source, "postback": {"data": f"fit={answer}"}}])
    assert any("最需要確認" in reply for reply in client.replies)
    assert any("原廠 AC 充電線" in reply for reply in client.replies)
