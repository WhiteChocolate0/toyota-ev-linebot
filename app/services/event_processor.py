import hashlib
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs
from collections.abc import Iterable

from app.services.cost_flow import cost_flow_manager
from app.services.comparison_context import comparison_context_manager
from app.services.faq_templates import source_id_for
from app.services.intent_triggers import has_explicit_cost_period, is_cost_calculator_trigger
from app.services.line_client import LineClient
from app.services.message_router import route_text_message
from app.services.message_preprocessor import normalize_bot_reference
from app.services.vehicle_need_router import vehicle_need_router
from app.services.mileage_parser import MileageParser, mileage_parser
from app.services.flow_intent import route_flow_intent
from app.services.persona_rewriter import PersonaRewriter, persona_rewriter
from app.services.powertrain import BEV, HEV, ICE_DIESEL, ICE_GASOLINE, PHEV, normalize_powertrain
from app.services.linebot_repository import LinebotRepository, get_repository
from app.services.vehicle_matcher import (
    is_explicit_vehicle_comparison,
    find_vehicles_in_text,
    vehicle_conversation_reply,
)
from app.services.vehicle_price import disambiguation_answer, price_answer, resolve_vehicle_price
from app.services.vehicle_carousel import build_vehicle_carousel
from app.services.cost_result_flex import build_cost_result_flex, build_full_cost_result_flex, build_share_card
from app.services.ev_fit_flow import ev_fit_manager
from app.services.ev_fit_flex import build_ev_fit_flex
from app.services.ev_advantage_flex import EV_TAX_BENEFIT_DETAIL, build_ev_tax_benefit_flex
from app.services.group_intelligence import analyse_group_message
from app.services.service_menu_flex import build_first_use_menu_flex, build_service_menu_flex, build_private_service_menu
from app.services.recommendation_engine import recommendation_engine, recommendation_readiness, shortlist_candidates
from app.services.recommendation_flex import build_recommendation_flex
from app.services.conversation_context import conversation_context_manager
from app.services.knowledge_retriever import RetrievedEvidence, knowledge_retriever
from app.services.evidence_validator import EvidenceAssessment, assess_evidence
from app.services.answer_composer import compose_answer
from app.services.vehicle_comparison import build_comparison_flex, comparison_text, vehicle_comparison_manager
from app.services.concern_board import build_concern_board, concern_type, status_from_signal
from app.services.campaign_handoff import normalize_campaign_summary, parse_campaign_handoff_token

logger = logging.getLogger(__name__)


def append_official_source(text: str, source: dict | None) -> str:
    if not source:
        return text
    return text + "\n\n" + format_source_for_user(source)


def format_source_for_user(source: dict) -> str:
    """Keep full timestamps for governance, never expose them verbatim to users."""
    publisher = source.get("publisher")
    title, url = source.get("title", "官方資料"), source.get("url", "")
    time_sensitive = any(word in str(source.get("category", "")) + " " + title for word in ("POLICY", "稅", "價格", "保固", "優惠"))
    verified = source.get("verified_at")
    date = f"\n資料確認：{str(verified)[:10].replace('-', '/')}" if time_sensitive and verified else ""
    heading = f"官方來源｜{publisher}\n{title}" if publisher else f"官方來源｜{title}"
    return f"{heading}{date}\n{url}"


def flow_scope(source: dict) -> str:
    user_id = source.get("userId") or "anonymous"
    group_id = source.get("groupId")
    raw_id = f"group:{group_id}:user:{user_id}" if group_id else f"user:{user_id}"
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


class EventProcessor:
    """Webhook event processing with source-backed replies and utility flows."""

    def __init__(
        self,
        line_client: LineClient | None = None,
        repository: LinebotRepository | None = None,
        rewriter: PersonaRewriter | None = None,
        parser: MileageParser | None = None,
    ) -> None:
        self._processed_ids: set[str] = set()
        self._line_client = line_client or LineClient()
        self._repository = repository if repository is not None else get_repository()
        self._rewriter = rewriter or persona_rewriter
        self._mileage_parser = parser or mileage_parser

    def _reply_cost_flow(self, reply_token: str, scope_id: str, text: str) -> None:
        items = cost_flow_manager.quick_reply_items(scope_id) if cost_flow_manager.is_active(scope_id) else []
        quick_reply = getattr(self._line_client, "reply_text_with_quick_replies", None)
        if items and callable(quick_reply):
            quick_reply(reply_token, text, items)
        else:
            self._line_client.reply_text(reply_token, text)

    def _reply_ev_fit(self, reply_token: str, scope_id: str, text: str) -> None:
        items = ev_fit_manager.quick_reply_items(scope_id)
        quick_reply = getattr(self._line_client, "reply_text_with_quick_replies", None)
        if items and callable(quick_reply):
            quick_reply(reply_token, text, items)
        elif hasattr(self._line_client, "reply_flex"):
            self._line_client.reply_flex(reply_token, build_ev_fit_flex(text))
        else:
            self._line_client.reply_text(reply_token, text)

    def _reply_group_summary(self, reply_token: str, text: str) -> None:
        items = [
            {"type": "action", "action": {"type": "postback", "label": "重新累積", "data": "group_summary=reset"}},
            {"type": "action", "action": {"type": "postback", "label": "刪除摘要", "data": "group_summary=delete"}},
        ]
        quick = getattr(self._line_client, "reply_text_with_quick_replies", None)
        if callable(quick):
            quick(reply_token, text, items)
        else:
            self._line_client.reply_text(reply_token, text)

    def _reply_concern_board(self, reply_token: str, group_id: str) -> None:
        rows = self._repository.concern_board(group_id) if self._repository and hasattr(self._repository, "concern_board") else []
        text = build_concern_board(rows)
        items = [{"type": "action", "action": {"type": "postback", "label": "這題已釐清", "data": "concern_status=CLARIFIED"}}, {"type": "action", "action": {"type": "postback", "label": "還有疑問", "data": "concern_status=OPEN"}}, {"type": "action", "action": {"type": "postback", "label": "稍後確認", "data": "concern_status=NEEDS_VERIFICATION"}}]
        quick = getattr(self._line_client, "reply_text_with_quick_replies", None)
        quick(reply_token, text, items) if callable(quick) else self._line_client.reply_text(reply_token, text)

    def _import_campaign_handoff(self, reply_token: str, scope_id: str, source: dict, token: str) -> None:
        consume = getattr(self._repository, "consume_campaign_token", None) if self._repository else None
        result = consume(token, source.get("userId", "")) if callable(consume) else {"status": "unavailable"}
        status = result.get("status")
        if status == "SUCCESS":
            now = datetime.now(UTC)
            summary = normalize_campaign_summary(result.get("result_summary"))
            persona_key = result.get("persona_key")
            self._hydrate_context(scope_id, source)
            slots = {
                "campaign_quiz_result_id": str(result.get("quiz_result_id", "")),
                "campaign_persona_key": persona_key,
                "campaign_ability_scores": result.get("ability_scores", {}),
                "campaign_summary": summary,
                "campaign_received_at": now.isoformat(),
                "campaign_expires_at": (now + timedelta(minutes=30)).isoformat(),
            }
            conversation_context_manager.update(scope_id, topic="CAMPAIGN_HANDOFF", goal="LEARN", slots=slots, intent="CAMPAIGN_HANDOFF")
            self._persist_context(scope_id, source)
            persona = summary.get("persona_name")
            intro = f"你剛剛在挑戰裡偏向「{persona}」，" if persona else "你剛剛的挑戰結果，"
            self._line_client.reply_text(reply_token, f"已帶入活動結果。{intro}我可以先從成本或實際用車條件開始幫你整理；這只會作為這次對話的提示。")
        elif status == "TOKEN_EXPIRED":
            self._line_client.reply_text(reply_token, "這份活動結果連結已失效，可以重新完成挑戰後再帶結果過來。")
        elif status == "TOKEN_ALREADY_CONSUMED":
            self._hydrate_context(scope_id, source)
            context = conversation_context_manager.get(scope_id)
            if context and context.slots.get("campaign_quiz_result_id") == result.get("quiz_result_id"):
                self._line_client.reply_text(reply_token, "這份結果已經帶進來過了。你想從成本、充電條件或車款比較繼續都可以。")
            else:
                self._line_client.reply_text(reply_token, "這份結果連結已經使用過，請回到活動網站重新產生接續連結。")
        elif status == "RESULT_NOT_FOUND":
            self._line_client.reply_text(reply_token, "目前找不到這份活動結果，可以重新完成挑戰後再試一次。")
        elif status == "TOKEN_NOT_FOUND":
            self._line_client.reply_text(reply_token, "這個活動結果連結無法使用，可以重新完成挑戰後再試一次。")
        else:
            self._line_client.reply_text(reply_token, "目前無法讀取這份活動結果，請確認連結後再試。")

    def _reply_group_handoff_private_only(self, reply_token: str) -> None:
        self._line_client.reply_text(reply_token, "活動結果請到與電車解惑所的 1 對 1 聊天中開啟，避免把個人測驗結果貼在群組裡。")

    def _reply_service_menu(self, reply_token: str, intro: str = "我在 🙋‍♀️\n直接問我問題也可以，或從下面開始：", source_type: str = "group") -> None:
        if hasattr(self._line_client, "reply_text_and_flex"):
            self._line_client.reply_text_and_flex(reply_token, intro, build_private_service_menu() if source_type == "user" else build_service_menu_flex())
        else:
            self._line_client.reply_text(reply_token, intro)

    def _member_needs_onboarding(self, source: dict) -> tuple[str | None, bool]:
        if source.get("type") != "group" or not self._repository:
            return None, False
        touch = getattr(self._repository, "touch_group", None)
        check = getattr(self._repository, "member_needs_onboarding", None)
        group_id = touch(source.get("groupId", "")) if callable(touch) else None
        return group_id, bool(group_id and callable(check) and check(group_id, source.get("userId", "")))

    def _bz4x_home_110v_feature(self) -> str | None:
        lookup = getattr(self._repository, "get_vehicle_feature", None) if self._repository else None
        if not callable(lookup):
            return None
        feature = lookup("bZ4X", "HOME_110V_CHARGING")
        return str(feature.get("description")) if feature and feature.get("description") else None

    def _reply_routed_faq(self, reply_token: str, source: dict, routed_reply: object, question_text: str) -> None:
        """Reply to a relevant FAQ without changing any user-owned wizard state."""
        quick_replies = getattr(routed_reply, "quick_replies", None)
        send_quick_replies = getattr(self._line_client, "reply_text_with_quick_replies", None)
        if quick_replies and source.get("type") == "user" and callable(send_quick_replies):
            send_quick_replies(reply_token, getattr(routed_reply, "text"), quick_replies)
            return
        concern_code = getattr(routed_reply, "concern_code", None)
        source_type = source.get("type", "unknown")
        conversation_context_manager.update(flow_scope(source), topic=concern_code, goal="LEARN", intent=concern_code)
        group_id = None
        if self._repository and source_type == "group" and concern_code:
            group_id = self._repository.touch_group(source.get("groupId", ""))
            if group_id:
                signal = analyse_group_message(question_text)
                record = getattr(self._repository, "record_group_signal", None)
                if callable(record):
                    record(group_id, source.get("userId", ""), signal.topic, signal.stance, signal.labels)
                else:
                    self._repository.record_concern(group_id, concern_code)
                board_type = concern_type(signal.topic)
                update_board = getattr(self._repository, "update_concern_board", None)
                if board_type and callable(update_board):
                    update_board(group_id, board_type, status_from_signal(board_type, signal.stance))
        official_source = None
        assessment = EvidenceAssessment("INSUFFICIENT", None)
        if self._repository and concern_code:
            classification = getattr(routed_reply, "classification", None)
            results = knowledge_retriever.retrieve(self._repository, question_text, getattr(classification, "topic", concern_code))
            assessment = assess_evidence(results)
            source_id = source_id_for(concern_code, question_text)
            lookup_source = getattr(self._repository, "get_knowledge_source", None)
            if assessment.evidence:
                official_source = assessment.evidence.source
            elif source_id and callable(lookup_source):
                official_source = lookup_source(source_id)
                if official_source:
                    assessment = EvidenceAssessment("STRONG", RetrievedEvidence(official_source, 1.0, ("category",)))
            if assessment.status == "INSUFFICIENT":
                record_gap = getattr(self._repository, "record_knowledge_gap", None)
                if callable(record_gap):
                    query_hash = hashlib.sha256(question_text.encode("utf-8")).hexdigest()
                    record_gap(query_hash, concern_code, results[0].score if results else None)
        # Source bodies are evidence only: a reviewed short answer is composed
        # and then cited, never pasted verbatim into the LINE reply.
        answer, citation_source = compose_answer(question_text, getattr(routed_reply, "text"), assessment)
        official_source = citation_source
        is_advantage_question = any(word in question_text for word in ("優勢", "好處", "特色", "有什麼"))
        if concern_code in {"TOYOTA_EV", "EV_GENERAL_OPINION"} and is_advantage_question and hasattr(self._line_client, "reply_flex"):
            self._line_client.reply_flex(reply_token, build_ev_tax_benefit_flex())
            return
        answer = append_official_source(answer, official_source)
        # A side question should not make a wizard feel abandoned.  Keep this
        # deliberately short; never paste the previous full prompt again.
        scope_id = flow_scope(source)
        answer += self._flow_resume_hint(scope_id)
        profile_group_id, needs_onboarding = self._member_needs_onboarding(source)
        if needs_onboarding and hasattr(self._line_client, "reply_text_and_flex"):
            self._line_client.reply_text_and_flex(reply_token, answer, build_first_use_menu_flex())
            mark = getattr(self._repository, "mark_member_onboarded", None) if self._repository else None
            if profile_group_id and callable(mark):
                mark(profile_group_id, source.get("userId", ""))
        else:
            self._line_client.reply_text(reply_token, answer)

    @staticmethod
    def _flow_resume_hint(scope_id: str) -> str:
        if cost_flow_manager.is_active(scope_id):
            stage = cost_flow_manager.current_stage(scope_id)
            hints = {
                "monthly_km": "\n\n剛剛的成本試算還在，接下來只要告訴我每月大約開多少公里就可以。",
                "ownership_years": "\n\n剛剛的成本試算還在，接下來只要告訴我預計持有幾年就可以。",
                "calculation_mode": "\n\n剛剛的成本試算還在，請選快速或精準試算。",
            }
            return hints.get(stage, "\n\n剛剛的成本試算還在，完成目前這一題就能繼續。")
        if ev_fit_manager.is_active(scope_id):
            stage = ev_fit_manager._states[scope_id].stage
            return "\n\n剛剛的評估還在等你的長途頻率。" if stage == "long_trip" else "\n\n剛剛的 EV 評估還在，完成目前這一題就能繼續。"
        return ""

    def _reply_vehicle_need(self, reply_token: str, route: object) -> None:
        """Reply to a structured vehicle preference without mutating other flows."""
        quick = getattr(self._line_client, "reply_text_with_quick_replies", None)
        items = getattr(route, "quick_replies", [])
        if items and callable(quick):
            quick(reply_token, str(getattr(route, "text")), items)
        else:
            self._line_client.reply_text(reply_token, str(getattr(route, "text")))

    def _handle_recommendation(self, reply_token: str, scope_id: str, source: dict, text: str) -> bool:
        """Update one user's nullable profile, then ask only for the next useful fact."""
        profile = recommendation_engine.update(scope_id, text)
        group_id = None
        if source.get("type") == "group" and self._repository:
            touch = getattr(self._repository, "touch_group", None)
            save = getattr(self._repository, "save_vehicle_preference_profile", None)
            group_id = touch(source.get("groupId", "")) if callable(touch) else None
            if group_id and callable(save):
                save(group_id, source.get("userId", ""), recommendation_engine.serialise(profile))
        follow_up = recommendation_readiness(profile)
        if follow_up:
            prefix = "我知道你重視空間需求。\n" if profile.cargo_space_priority else ""
            self._line_client.reply_text(reply_token, prefix + follow_up)
            return True
        lookup = getattr(self._repository, "list_recommendation_profiles", None) if self._repository else None
        vehicles = lookup() if callable(lookup) else []
        candidates = shortlist_candidates(profile, vehicles)
        if candidates and hasattr(self._line_client, "reply_flex"):
            self._line_client.reply_flex(reply_token, build_recommendation_flex(candidates))
        elif candidates:
            self._line_client.reply_text(reply_token, "依你目前的需求，可以先比較：" + "、".join(str(item.vehicle["model_name"]) for item in candidates))
        else:
            self._line_client.reply_text(reply_token, "目前沒有足夠的官方車款資料能安全列出候選車；可先比較其他車款，或確認預算與動力偏好。")
        return True

    def _persist_context(self, scope_id: str, source: dict) -> None:
        context = conversation_context_manager.get(scope_id)
        if not context or not self._repository:
            return
        save = getattr(self._repository, "save_conversation_context", None)
        group_id = None
        if source.get("type") == "group":
            touch = getattr(self._repository, "touch_group", None)
            group_id = touch(source.get("groupId", "")) if callable(touch) else None
            if not group_id:
                return
        if callable(save):
            # Do not silently claim a context was saved when the source of truth
            # rejected the write. The warm cache remains only an optimisation.
            if save(group_id, source.get("userId", ""), context.payload(), context.expires_at.isoformat()) is False:
                logger.error("Conversation context persistence failed", extra={"scope_id": scope_id})

    def _hydrate_context(self, scope_id: str, source: dict) -> None:
        row = None
        if self._repository:
            lookup = getattr(self._repository, "get_conversation_context", None)
            group_id = None
            if source.get("type") == "group":
                touch = getattr(self._repository, "touch_group", None)
                group_id = touch(source.get("groupId", "")) if callable(touch) else None
                if not group_id:
                    lookup = None
            row = lookup(group_id, source.get("userId", "")) if callable(lookup) else None
        _, context_source = conversation_context_manager.hydrate(scope_id, row)
        logger.info("Conversation context loaded", extra={"context_source": context_source, "scope_id": scope_id})

    def _record_vehicle_entities(self, scope_id: str, source: dict, text: str) -> None:
        if not self._repository:
            return
        list_profiles = getattr(self._repository, "list_active_vehicle_profiles", None)
        profiles = list_profiles() if callable(list_profiles) else []
        matches = find_vehicles_in_text(text, profiles)
        ids = [str(item.get("id")) for item in matches if item.get("id")]
        if not ids:
            return
        operation = "REPLACE"
        if any(token in text for token in ("改成", "換成", "不要", "移除")):
            operation = "REMOVE" if any(token in text for token in ("不要", "移除")) else "REPLACE"
        elif any(token in text for token in ("再加", "加上", "也加")):
            operation = "ADD"
        goal = "COMPARE" if len(ids) >= 2 or any(token in text for token in ("比較", "哪台", "哪個")) else None
        conversation_context_manager.update(scope_id, vehicle_ids=ids, entity_operation=operation, active_vehicle_id=ids[0] if len(ids) == 1 else None, goal=goal, intent="VEHICLE_ENTITY")
        self._persist_context(scope_id, source)

    def _reply_vehicle_price(self, reply_token: str, scope_id: str, source: dict, message_text: str) -> bool:
        """Resolve sale price from the catalogue before FAQ/RAG or TCO routing."""
        if not self._repository:
            return False
        list_profiles = getattr(self._repository, "list_active_vehicle_profiles", None)
        if not callable(list_profiles):
            return False
        context = conversation_context_manager.get(scope_id)
        resolution = resolve_vehicle_price(message_text, context.active_vehicle_id if context else None, list_profiles())
        if not resolution:
            return False
        if resolution.kind == "NEED_VEHICLE":
            self._line_client.reply_text(reply_token, "你想問哪一台車的價格？可以直接告訴我車名。")
            return True
        if resolution.kind == "DISAMBIGUATE":
            self._line_client.reply_text(reply_token, disambiguation_answer(resolution.profiles))
            return True
        profile = resolution.profiles[0]
        source_url = profile.get("source_url")
        answer = price_answer(profile)
        if source_url:
            answer = append_official_source(answer, {"publisher": "TOYOTA Taiwan", "title": f"{profile.get('model_name', '車款')} 官方車款資料", "url": source_url})
        items = [
            {"type": "action", "action": {"type": "postback", "label": "比較其他車款", "data": "action=start_vehicle_comparison"}},
            {"type": "action", "action": {"type": "postback", "label": "算用車成本", "data": "action=start_cost_compare"}},
        ]
        quick = getattr(self._line_client, "reply_text_with_quick_replies", None)
        if callable(quick):
            quick(reply_token, answer, items)
        else:
            self._line_client.reply_text(reply_token, answer)
        return True

    @staticmethod
    def _is_flow_side_query(text: str) -> bool:
        return any(word in text for word in ("電池", "保固", "續航", "充電", "安全", "貨物稅", "優勢", "好處")) and not any(char.isdigit() for char in text)

    def _persist_cost_calculation(self, scope_id: str) -> None:
        """Best-effort persistence; result delivery never depends on Supabase availability."""
        save = getattr(self._repository, "save_cost_calculation", None) if self._repository else None
        snapshot = cost_flow_manager.calculation_snapshot(scope_id)
        if snapshot and callable(save):
            save(snapshot)

    def _persist_group_flow(self, scope_id: str, source: dict) -> None:
        if not self._repository:
            return
        snapshot = cost_flow_manager.flow_snapshot(scope_id)
        save = getattr(self._repository, "save_conversation_flow", None)
        if snapshot and callable(save):
            group_id = None
            if source.get("type") == "group":
                touch = getattr(self._repository, "touch_group", None)
                group_id = touch(source.get("groupId", "")) if callable(touch) else None
                if not group_id:
                    return
            save(group_id, source.get("userId", ""), snapshot)

    def _persist_vehicle_comparison(self, scope_id: str, source: dict) -> None:
        if not self._repository:
            return
        session = vehicle_comparison_manager.get(scope_id)
        save = getattr(self._repository, "save_vehicle_comparison_session", None)
        if not session or not callable(save) or len(session.vehicle_ids) < 2:
            return
        group_id = None
        if source.get("type") == "group":
            touch = getattr(self._repository, "touch_group", None)
            group_id = touch(source.get("groupId", "")) if callable(touch) else None
            if not group_id:
                return
        if save(group_id, source.get("userId", ""), session.vehicle_ids, session.dimensions, source_type=source.get("type", "user")) is False:
            logger.error("Vehicle comparison session persistence failed", extra={"scope_id": scope_id})

    def _cancel_persisted_flows(self, source: dict) -> None:
        if not self._repository:
            return
        group_id = None
        if source.get("type") == "group":
            touch = getattr(self._repository, "touch_group", None)
            group_id = touch(source.get("groupId", "")) if callable(touch) else None
            if not group_id:
                return
        cancel = getattr(self._repository, "cancel_active_conversation_flows", None)
        if callable(cancel):
            cancel(group_id, source.get("userId", ""))
        cancel_comparison = getattr(self._repository, "cancel_vehicle_comparison_session", None)
        if callable(cancel_comparison):
            cancel_comparison(group_id, source.get("userId", ""))

    def _matched_vehicle_reply(self, message_text: str, source_type: str, line_user_id: str = "") -> str | None:
        """Confirm a personal vehicle mention without making a group interruption."""
        if not self._repository:
            return None
        list_profiles = getattr(self._repository, "list_active_vehicle_profiles", None)
        if not callable(list_profiles):
            return None
        profiles = find_vehicles_in_text(message_text, list_profiles())
        if not profiles:
            return None
        if source_type == "group" and not is_explicit_vehicle_comparison(message_text):
            return None
        if source_type == "user" and self._rewriter.is_enabled:
            self._line_client.show_loading_animation(line_user_id)
        fallback = vehicle_conversation_reply(profiles, source_type)
        return self._rewriter.rewrite_vehicle_reply(
            fallback=fallback,
            message_text=message_text,
            source_type=source_type,
            model_names=tuple(profile["model_name"] for profile in profiles),
        )

    @staticmethod
    def _start_comparison_cost_flow(scope_id: str, drivetrain: str | None, source: dict) -> str:
        cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", ""))
        vehicle_type = normalize_powertrain(drivetrain or "")
        if vehicle_type:
            prompt = cost_flow_manager.advance(scope_id, vehicle_type)
            return f"好呀！先從日常用車開始：{prompt}"
        return "好呀！先從目前用車開始：" + cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", ""))

    def process(self, events: Iterable[dict]) -> None:
        for event in events:
            event_id = event.get("webhookEventId") or event.get("message", {}).get("id")
            if event_id and event_id in self._processed_ids:
                logger.info("Skipping duplicate LINE event", extra={"event_id": event_id})
                continue
            if event_id:
                self._processed_ids.add(event_id)
                if self._repository and self._repository.claim_event(event_id) is False:
                    logger.info("Skipping duplicate persisted LINE event")
                    continue

            source = event.get("source", {})
            source_type = source.get("type", "unknown")
            scope_id = flow_scope(source)
            event_type = event.get("type")
            logger.info("Received LINE event", extra={"event_type": event_type, "source_type": source_type})
            reply_token = event.get("replyToken")
            if event_type == "join" and source_type == "group" and reply_token:
                self._line_client.reply_group_welcome(reply_token)
                continue
            if event_type == "follow" and source_type == "user" and reply_token:
                welcome = "嗨，我是『電車解惑所』⚡\n\n想了解電動車，不用先懂一堆規格。\n不管你是在想『適不適合換電車』、正在挑車，還是只想問電池、充電、續航或養車成本，都可以直接問我。\n\n我會盡量用好懂的方式整理，重要規格、政策或保固資訊也會以可查證的官方資料為主。\n\n不知道從哪裡開始也沒關係，從下面選一個就好 👇"
                self._reply_service_menu(reply_token, welcome, source_type="user")
                mark = getattr(self._repository, "mark_private_onboarded", None) if self._repository else None
                if callable(mark): mark(source.get("userId", ""))
                logger.info("Private welcome menu sent", extra={"event_type": "follow", "source_type": "user", "menu_builder": "private", "menu_sent": True})
                continue

            message = event.get("message", {})
            if event_type == "postback" and reply_token:
                data = event.get("postback", {}).get("data", "")
                params = parse_qs(data)
                campaign_token = parse_campaign_handoff_token(data)
                if campaign_token is not None:
                    if source_type != "user":
                        self._reply_group_handoff_private_only(reply_token)
                    else:
                        self._import_campaign_handoff(reply_token, scope_id, source, campaign_token)
                    continue
                summary_action = params.get("group_summary", [""])[0]
                if summary_action and source_type == "group":
                    touch = getattr(self._repository, "touch_group", None) if self._repository else None
                    group_id = touch(source.get("groupId", "")) if callable(touch) else None
                    if group_id and self._repository:
                        if summary_action == "show":
                            self._reply_group_summary(reply_token, self._repository.group_summary(group_id))
                        elif summary_action in {"reset", "delete"}:
                            self._line_client.reply_text(reply_token, self._repository.clear_group_summary(group_id, delete=summary_action == "delete"))
                    continue
                board_status = params.get("concern_status", [""])[0]
                if board_status and source_type == "group" and self._repository:
                    # Status applies to the most recently surfaced concern only;
                    # user-facing board avoids assigning people or opinions.
                    group_id = self._repository.touch_group(source.get("groupId", ""))
                    rows = self._repository.concern_board(group_id) if hasattr(self._repository, "concern_board") else []
                    if rows and hasattr(self._repository, "set_concern_board_status"):
                        self._repository.set_concern_board_status(group_id, rows[0]["concern_type"], board_status)
                    self._reply_concern_board(reply_token, group_id)
                    continue
                action = params.get("action", [""])[0]
                if action == "cancel_flow":
                    self._cancel_persisted_flows(source)
                    flow_id = params.get("flow_id", [""])[0]
                    if flow_id == "EV_FIT":
                        ev_fit_manager._states.pop(scope_id, None); self._line_client.reply_text(reply_token, "已結束這次 EV 使用評估。")
                    elif flow_id == "COST_CALCULATION":
                        cost_flow_manager.cancel(scope_id); self._persist_group_flow(scope_id, source); self._line_client.reply_text(reply_token, "已結束這次成本試算。之後想再開始，直接輸入「成本試算」就可以。")
                    elif flow_id == "VEHICLE_RECOMMENDATION":
                        recommendation_engine.clear(scope_id); vehicle_need_router.clear(scope_id); self._line_client.reply_text(reply_token, "已結束這次選車流程。")
                    else:
                        comparison_context_manager.clear(scope_id); self._line_client.reply_text(reply_token, "已結束這次比較。")
                    continue
                if action == "show_service_menu":
                    self._reply_service_menu(reply_token, source_type=source_type)
                    continue
                if action == "start_ev_fit":
                    conversation_context_manager.update(scope_id, intent="START_EV_FIT")
                    context = conversation_context_manager.get(scope_id)
                    if context: context.last_active_flow = "EV_FIT"
                    self._reply_ev_fit(reply_token, scope_id, ev_fit_manager.start(scope_id))
                    continue
                if action == "start_cost_compare":
                    conversation_context_manager.update(scope_id, intent="START_COST_COMPARE")
                    context = conversation_context_manager.get(scope_id)
                    if context: context.last_active_flow = "COST_CALCULATION"
                    self._reply_cost_flow(reply_token, scope_id, "💰 成本比較\n" + cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", "")))
                    self._persist_group_flow(scope_id, source)
                    continue
                if action == "start_vehicle_comparison":
                    self._line_client.reply_text(reply_token, "想比較哪些車？可以直接打車名，也可以從車款清單選；選 2–3 台後我會先整理整體差異。")
                    continue
                if action == "invite_to_family_group":
                    self._line_client.reply_text(reply_token, "想跟家人一起討論嗎？\n1. 打開家庭 LINE 群組\n2. 點右上角選單\n3. 選擇邀請\n4. 搜尋「電車解惑所」並邀請加入。")
                    continue
                if action == "view_recent_results":
                    lookup = getattr(self._repository, "recent_user_results", None) if self._repository else None
                    rows = lookup(source.get("userId", "")) if callable(lookup) else []
                    if not rows:
                        self._line_client.reply_text(reply_token, "目前還沒有完成過的結果。可以先從 EV 適配、幫我選車或比較車款與成本開始。")
                    else:
                        labels = {"EV_FIT": "EV 評估", "VEHICLE_COMPARISON": "車款比較", "COST_CALCULATION": "成本試算", "FULL_TCO": "完整持有成本", "VEHICLE_RECOMMENDATION": "選車結果"}
                        text = "想看哪一個？\n" + "\n".join(f"・{labels.get(row['result_type'], row['result_type'])}｜{str(row['completed_at'])[:10].replace('-', '/')}" for row in rows)
                        self._line_client.reply_text(reply_token, text)
                    continue
                if action == "start_vehicle_recommendation":
                    self._line_client.reply_text(reply_token, "告訴我你在意的空間、預算、通勤或長途需求；例如「家裡五個人、常出遊、預算 130 萬」。")
                    continue
                if action == "add_candidate_to_cost":
                    vehicle_id = params.get("vehicle_id", [""])[0]
                    lookup = getattr(self._repository, "get_active_vehicle_profile_by_id", None) if self._repository else None
                    selected = lookup(vehicle_id) if callable(lookup) else None
                    if selected:
                        cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", ""))
                        cost_flow_manager.advance(scope_id, str(selected.get("drivetrain", "")))
                        reply = cost_flow_manager.select_vehicle_profile(scope_id, "A", selected)
                        self._reply_cost_flow(reply_token, scope_id, "已先加入「" + str(selected.get("model_name", "")) + "」作為比較車：\n" + (reply or "請選下一台車。"))
                    else:
                        self._line_client.reply_text(reply_token, "這個候選車款已更新，請重新取得推薦。")
                    continue
                if action == "comparison_cost_pair":
                    lookup = getattr(self._repository, "get_active_vehicle_profile_by_id", None) if self._repository else None
                    first, second = params.get("a", [""])[0], params.get("b", [""])[0]
                    a, b = (lookup(first) if callable(lookup) else None), (lookup(second) if callable(lookup) else None)
                    if not a or not b:
                        self._line_client.reply_text(reply_token, "其中一台車款資料已更新，請重新開始比較。")
                        continue
                    cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", ""))
                    cost_flow_manager.advance(scope_id, str(a.get("drivetrain", ""))); cost_flow_manager.select_vehicle_profile(scope_id, "A", a)
                    cost_flow_manager.advance(scope_id, str(b.get("drivetrain", ""))); reply = cost_flow_manager.select_vehicle_profile(scope_id, "B", b)
                    self._reply_cost_flow(reply_token, scope_id, "已帶入「" + str(a.get("model_name")) + "」與「" + str(b.get("model_name")) + "」。\n" + (reply or cost_flow_manager.current_prompt(scope_id)))
                    continue
                if action == "cost_sensitivity_menu":
                    items = [{"type": "action", "action": {"type": "postback", "label": label, "data": f"action=run_scenario&scenario={code}"}} for label, code in (("里程變多", "HIGH_MILEAGE"), ("持有更久", "LONG_OWNERSHIP"), ("公共充電較多", "PUBLIC_CHARGING_HEAVY"), ("油價 +10%", "FUEL_PRICE_UP"), ("電價 +10%", "ELECTRICITY_PRICE_UP"))]
                    quick = getattr(self._line_client, "reply_text_with_quick_replies", None)
                    if callable(quick): quick(reply_token, "想看看哪個條件變動？", items)
                    else: self._line_client.reply_text(reply_token, "可選：里程變多、持有更久、公共充電較多、油價變動、電價變動。")
                    continue
                if action == "run_scenario":
                    outcome = cost_flow_manager.sensitivity(scope_id, params.get("scenario", [""])[0])
                    if outcome:
                        text, scenario = outcome
                        save = getattr(self._repository, "save_cost_scenario", None) if self._repository else None
                        if callable(save): save(scenario)
                        self._line_client.reply_text(reply_token, text)
                    else: self._line_client.reply_text(reply_token, "請先完成一組成本試算後再查看情境分析。")
                    continue
                if action == "open_ev_question_help":
                    self._line_client.reply_text(reply_token, "可以直接問我電池、充電、續航、保養、成本或 TOYOTA 車款；我會先提供可確認的方向。")
                    continue
                if action == "ev_tax_more":
                    self._line_client.reply_text(reply_token, EV_TAX_BENEFIT_DETAIL)
                    continue
                fit_value = params.get("fit", [""])[0]
                if fit_value:
                    if ev_fit_manager.is_active(scope_id):
                        fit_reply = ev_fit_manager.advance(scope_id, fit_value, self._bz4x_home_110v_feature())
                        self._reply_ev_fit(reply_token, scope_id, fit_reply)
                        if not ev_fit_manager.is_active(scope_id):
                            profile = recommendation_engine.apply_ev_fit(scope_id, ev_fit_manager._states[scope_id].values)
                            context = conversation_context_manager.get(scope_id)
                            if context: context.last_active_flow = None
                            if source_type == "group" and self._repository:
                                touch = getattr(self._repository, "touch_group", None)
                                save = getattr(self._repository, "save_vehicle_preference_profile", None)
                                group_id = touch(source.get("groupId", "")) if callable(touch) else None
                                if group_id and callable(save): save(group_id, source.get("userId", ""), recommendation_engine.serialise(profile))
                    elif source_type == "group":
                        self._line_client.reply_text(reply_token, "這份生活健檢目前由另一位成員操作中；你可輸入「EV 生活健檢」開始自己的版本。")
                    continue
                resume_choice = params.get("flow_resume", [""])[0]
                if resume_choice:
                    if resume_choice == "restart":
                        self._reply_cost_flow(reply_token, scope_id, cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", "")))
                    else:
                        resumed = cost_flow_manager.resume(scope_id)
                        if resumed:
                            self._reply_cost_flow(reply_token, scope_id, "好的，繼續剛剛的成本試算。\n" + resumed)
                    continue
                result_action = cost_flow_manager.result_action(scope_id, action, params, source_type) if action else None
                if result_action:
                    text, items = result_action
                    if action == "save_calculation":
                        self._persist_cost_calculation(scope_id)
                    if action == "generate_share_card" and hasattr(self._line_client, "reply_flex"):
                        self._line_client.reply_flex(reply_token, build_share_card(text))
                    elif action == "show_cost_result" and hasattr(self._line_client, "reply_flex"):
                        self._line_client.reply_flex(reply_token, build_cost_result_flex(text, cost_flow_manager.calculation_id(scope_id), source_type))
                    elif items and hasattr(self._line_client, "reply_text_with_quick_replies"):
                        self._line_client.reply_text_with_quick_replies(reply_token, text, items)
                    else:
                        self._line_client.reply_text(reply_token, text)
                    continue
                if source_type == "group" and not cost_flow_manager.is_active(scope_id):
                    owner = cost_flow_manager.group_flow_owner(source.get("groupId", ""))
                    if owner and owner != source.get("userId"):
                        self._line_client.reply_text(reply_token, "這次試算目前由另一位成員操作中；如果你也想試算，可以輸入「成本試算」開始自己的版本。")
                        continue
                if params.get("action") == ["select_vehicle"]:
                    slot, vehicle_id = params.get("slot", [""])[0], params.get("vehicle_id", [""])[0]
                    lookup = getattr(self._repository, "get_active_vehicle_profile_by_id", None) if self._repository else None
                    selected = lookup(vehicle_id) if callable(lookup) else None
                    reply = cost_flow_manager.select_vehicle_profile(scope_id, slot, selected) if selected else None
                    if reply:
                        self._reply_cost_flow(reply_token, scope_id, reply)
                    else:
                        self._line_client.reply_text(reply_token, "這個車款選項已失效，請重新選擇。")
                    continue
                key, _, value = data.partition("=")
                if key in {"powertrain", "model", "mileage", "mode", "years", "phev_preset", "full_cost"}:
                    if key == "mileage" and value == "custom":
                        message_text = "自己輸入"
                    else:
                        message_text = value
                else:
                    continue
            elif event_type == "message" and message.get("type") == "text" and reply_token:
                message_text = message.get("text", "")
            else:
                continue
            campaign_token = parse_campaign_handoff_token(message_text) if event_type == "message" else None
            if campaign_token is not None:
                if source_type != "user":
                    self._reply_group_handoff_private_only(reply_token)
                else:
                    self._import_campaign_handoff(reply_token, scope_id, source, campaign_token)
                continue
            prepared = normalize_bot_reference(message_text)
            if prepared.is_bot_invocation:
                self._reply_service_menu(reply_token, "想做什麼？從下面選一個就好 👇" if source_type == "user" else "我在 🙋‍♀️\n直接問我問題也可以，或從下面開始：", source_type=source_type)
                continue
            if not prepared.text:
                # A bare name / @mention intentionally triggers neither FAQ,
                # retrieval, nor an in-progress calculator field parser.
                continue
            message_text = prepared.text
            # This happens on every request after normalisation: a cold Vercel
            # instance must hydrate before any router can inherit semantics.
            self._hydrate_context(scope_id, source)
            self._record_vehicle_entities(scope_id, source, message_text)
            if message_text.strip().casefold() in {
                "功能", "選單", "功能選單", "你可以做什麼", "你會什麼", "怎麼用", "如何使用", "help", "menu"
            }:
                self._reply_service_menu(reply_token, "想做什麼？從下面選一個就好 👇" if source_type == "user" else "我在 🙋‍♀️\n直接問我問題也可以，或從下面開始：", source_type=source_type)
                continue
            if source_type == "group" and message_text.strip() in {"目前還有什麼問題？", "整理一下", "整理 EV 討論", "幫我整理", "我們討論到哪？", "疑慮"}:
                touch = getattr(self._repository, "touch_group", None) if self._repository else None
                group_id = touch(source.get("groupId", "")) if callable(touch) else None
                if group_id and self._repository:
                    self._reply_concern_board(reply_token, group_id)
                else:
                    self._line_client.reply_text(reply_token, "目前無法讀取群組摘要，請稍後再試。")
                continue
            if message_text.strip().casefold() in {"取消", "取消試算", "停止", "結束", "不要了", "退出"}:
                cancelled = cost_flow_manager.cancel(scope_id)
                comparison_context_manager.clear(scope_id)
                vehicle_need_router.clear(scope_id)
                recommendation_engine.clear(scope_id)
                # EV-fit is also an owned flow; remove its in-memory session.
                ev_fit_manager._states.pop(scope_id, None)
                self._cancel_persisted_flows(source)
                self._line_client.reply_text(reply_token, "好，已結束這次流程。之後想再開始時直接說「幫我選車」就可以。")
                continue
            if message_text.strip() in {"幫我選車", "我要選車", "推薦車款"}:
                recommendation_engine.clear(scope_id)
                vehicle_need_router.clear(scope_id)
                self._line_client.reply_text(reply_token, "可以。你目前最在意哪一件事？\n可先說預算、空間、省錢、長途、電動車，或直接描述你的需求。")
                continue
            # An explicit calculator command is always a fresh start.  In
            # particular, it must not be consumed as an answer to a stale
            # field in an unfinished one-to-one calculation.
            if is_cost_calculator_trigger(message_text):
                conversation_context_manager.update(scope_id, intent="START_COST_COMPARE")
                context = conversation_context_manager.get(scope_id)
                if context: context.last_active_flow = "COST_CALCULATION"
                self._reply_cost_flow(
                    reply_token,
                    scope_id,
                    "💰 成本試算\n我會幫你比較兩台 TOYOTA 的長期用車成本。\n\n" + cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", "")),
                )
                self._persist_group_flow(scope_id, source)
                continue
            if any(trigger in message_text for trigger in ("生活健檢", "我適合開電動車嗎", "生活適合 EV")):
                conversation_context_manager.update(scope_id, intent="START_EV_FIT")
                context = conversation_context_manager.get(scope_id)
                if context: context.last_active_flow = "EV_FIT"
                self._reply_ev_fit(reply_token, scope_id, ev_fit_manager.start(scope_id))
                continue
            # Price is a catalogue lookup, not an ownership-cost estimate.
            # It intentionally runs before contextual generic routing and RAG.
            if self._reply_vehicle_price(reply_token, scope_id, source, message_text):
                continue
            # Wizard answers have first priority; short-term topic continuation
            # never consumes a cost or EV-fit field.
            resolved = None if ev_fit_manager.is_active(scope_id) or cost_flow_manager.is_active(scope_id) else conversation_context_manager.resolve(scope_id, message_text)
            if resolved and resolved.resolved_using_context:
                conversation_context_manager.update(scope_id, topic=resolved.topic, goal=resolved.goal, slots=resolved.slots, intent="CONTEXT_INHERITED")
                self._persist_context(scope_id, source)
                self._handle_recommendation(reply_token, scope_id, source, message_text)
                continue
            # Preference-led selection is evaluated before FAQ and any active
            # calculator.  A phrase such as「想要後車廂大一點」must never be
            # consumed as a pending price or mileage field.
            active_flow = ev_fit_manager.is_active(scope_id) or cost_flow_manager.is_active(scope_id)
            # Explicit natural-language 2/3-car comparison is handled before
            # generic FAQ. A fourth candidate is never silently appended.
            profiles = []
            list_profiles = getattr(self._repository, "list_active_vehicle_profiles", None) if self._repository else None
            if callable(list_profiles): profiles = find_vehicles_in_text(message_text, list_profiles())
            if len(profiles) >= 2 and is_explicit_vehicle_comparison(message_text):
                session, over_limit = vehicle_comparison_manager.set_profiles(scope_id, profiles)
                if over_limit:
                    self._line_client.reply_text(reply_token, "目前一次最多比較 3 台，你想換掉哪一台？")
                else:
                    self._persist_vehicle_comparison(scope_id, source)
                    if hasattr(self._line_client, "reply_flex"):
                        self._line_client.reply_flex(reply_token, build_comparison_flex(session, recommendation_engine.profile(scope_id)))
                    else:
                        self._line_client.reply_text(reply_token, comparison_text(session, recommendation_engine.profile(scope_id)))
                # Preserve the existing affirmative shortcut for a two-car
                # conversation; the new card additionally offers pair choices.
                if len(profiles) == 2:
                    comparison_context_manager.offer(scope_id, profiles)
                continue
            # A real multi-step flow owns field answers. It is deliberately
            # checked before preference/FAQ routing below.
            # A topic request is a PAUSE_FOR_SIDE_QUERY result: it does not
            # consume the active wizard field and the flow remains resumable.
            vehicle_need = vehicle_need_router.route(scope_id, message_text)
            if vehicle_need:
                conversation_context_manager.update(
                    scope_id, topic=vehicle_need.classification.topic, goal=vehicle_need.classification.user_goal,
                    slots=vehicle_need.classification.slots, intent=vehicle_need.classification.topic,
                )
                self._persist_context(scope_id, source)
                self._handle_recommendation(reply_token, scope_id, source, message_text)
                continue
            profile = recommendation_engine.profile(scope_id)
            # Never let a remembered recommendation profile consume a message
            # merely because it contains a broad word such as「充電」or「長途」.
            # Only VehicleNeedRouter's explicit expected-input classification
            # may update preference slots.
            # A relevant FAQ is an intentional interruption, never a form value.
            # This also protects a cost-flow owner who asks a real question while
            # their wizard is waiting for a value, and leaves the state untouched.
            if not is_explicit_vehicle_comparison(message_text) and (not active_flow or self._is_flow_side_query(message_text)):
                signal = analyse_group_message(message_text) if source_type == "group" else None
                routed_faq = None if signal and signal.level == "L3" else route_text_message(message_text, source_type)
                if routed_faq:
                    self._reply_routed_faq(reply_token, source, routed_faq, message_text)
                    continue
            # L3 records an EV-related discussion statement without retaining
            # its body. It may offer one optional summary after repeated signals.
            if source_type == "group" and self._repository:
                signal = analyse_group_message(message_text)
                if signal.relevant and signal.level == "L3":
                    group_id = self._repository.touch_group(source.get("groupId", ""))
                    record = getattr(self._repository, "record_group_signal", None)
                    if group_id and callable(record) and record(group_id, source.get("userId", ""), signal.topic, signal.stance, signal.labels):
                        items = [
                            {"type": "action", "action": {"type": "postback", "label": "整理一下", "data": "group_summary=show"}},
                            {"type": "action", "action": {"type": "postback", "label": "先不用", "data": "group_summary=reset"}},
                        ]
                        quick = getattr(self._line_client, "reply_text_with_quick_replies", None)
                        text = "你們最近提到幾個 EV 用車條件；需要我只整理已知重點與下一步嗎？"
                        if callable(quick):
                            quick(reply_token, text, items)
                        else:
                            self._line_client.reply_text(reply_token, text)
                        continue
                    board_type = concern_type(signal.topic)
                    update_board = getattr(self._repository, "update_concern_board", None)
                    if group_id and board_type and callable(update_board):
                        update_board(group_id, board_type, status_from_signal(board_type, signal.stance))
            if ev_fit_manager.is_active(scope_id):
                self._reply_ev_fit(reply_token, scope_id, ev_fit_manager.advance(scope_id, message_text.strip(), self._bz4x_home_110v_feature()))
                continue
            if cost_flow_manager.pause_if_expired(scope_id) or cost_flow_manager.is_paused(scope_id):
                items = [
                    {"type": "action", "action": {"type": "postback", "label": "繼續", "data": "flow_resume=continue"}},
                    {"type": "action", "action": {"type": "postback", "label": "重新開始", "data": "flow_resume=restart"}},
                ]
                quick = getattr(self._line_client, "reply_text_with_quick_replies", None)
                text = "剛剛的成本試算還要繼續嗎？"
                if callable(quick): quick(reply_token, text, items)
                else: self._line_client.reply_text(reply_token, text)
                continue
            if cost_flow_manager.is_active(scope_id):
                cost_flow_manager.touch(scope_id)
                # Route cross-field answers before handing text to the current state.
                # This prevents a repeated mileage sentence being treated as an invalid
                # charging-ratio response.
                intent = route_flow_intent(message_text)
                edited = cost_flow_manager.apply_edit(scope_id, message_text)
                if edited is not None:
                    self._persist_cost_calculation(scope_id)
                    if hasattr(self._line_client, "reply_flex"):
                        self._line_client.reply_flex(reply_token, build_cost_result_flex(edited, cost_flow_manager.calculation_id(scope_id), source_type))
                    else:
                        self._line_client.reply_text(reply_token, edited)
                    continue
                if intent.intent == "restart":
                    self._reply_cost_flow(reply_token, scope_id, cost_flow_manager.start(scope_id, group_id=source.get("groupId", ""), owner_user_id=source.get("userId", "")))
                    continue
                if intent.intent == "cancel":
                    self._line_client.reply_text(reply_token, cost_flow_manager.cancel(scope_id) or "目前沒有進行中的試算。")
                    continue
                if intent.intent == "mileage_info" and not cost_flow_manager.expects_monthly_mileage(scope_id):
                    parsed = intent.payload
                    if getattr(parsed, "status", None) == "need_clarification":
                        self._line_client.reply_text(reply_token, parsed.reply)
                        continue
                    if getattr(parsed, "monthly_mileage", None) is not None:
                        self._line_client.reply_text(reply_token, cost_flow_manager.update_mileage(scope_id, parsed.monthly_mileage))
                        continue
                if intent.intent == "actual_efficiency":
                    self._line_client.reply_text(reply_token, cost_flow_manager.request_actual_efficiency(scope_id, message_text))
                    continue
                stage = cost_flow_manager.current_stage(scope_id)
                # A recognised answer for another field must not fall through to
                # the current field parser (for example, charging text at a price
                # prompt or a powertrain word at a mileage prompt).
                allowed_intents = {
                    "charging_ratio": {"charging_info", "answer_current_field"},
                    "ownership_years": {"ownership_years", "answer_current_field"},
                    "vehicle_type": {"powertrain_change", "answer_current_field"},
                    "vehicle_b_type": {"powertrain_change", "answer_current_field"},
                }
                if intent.intent != "answer_current_field" and intent.intent not in allowed_intents.get(stage, set()):
                    self._line_client.reply_text(reply_token, f"收到，這是「{intent.intent}」資訊；目前還需要：\n{cost_flow_manager.current_prompt(scope_id)}")
                    continue
                switched = cost_flow_manager.switch_vehicle_if_corrected(scope_id, message_text)
                if switched:
                    if self._repository:
                        lookup = getattr(self._repository, "get_active_vehicle_energy_profile", None)
                        if callable(lookup):
                            cost_flow_manager.set_official_efficiencies(scope_id, lookup(*switched))
                    self._line_client.reply_text(reply_token, cost_flow_manager.resume_after_vehicle_switch(scope_id))
                    continue
                selecting_model = cost_flow_manager.expects_vehicle_model(scope_id)
                mileage_confirmation = ""
                if cost_flow_manager.expects_monthly_mileage(scope_id):
                    if source_type == "user" and self._mileage_parser.is_enabled:
                        self._line_client.show_loading_animation(source.get("userId", ""))
                    parsed = self._mileage_parser.parse(message_text)
                    if parsed and parsed.status == "need_clarification":
                        self._line_client.reply_text(reply_token, parsed.reply)
                        continue
                    if parsed and parsed.monthly_mileage is not None:
                        message_text = str(parsed.monthly_mileage)
                        mileage_confirmation = parsed.reply + "\n"
                result = mileage_confirmation + cost_flow_manager.advance(scope_id, message_text)
                self._persist_group_flow(scope_id, source)
                if selecting_model and self._repository:
                    selected = cost_flow_manager.selected_vehicle(scope_id)
                    lookup = getattr(self._repository, "get_active_vehicle_energy_profile", None)
                    if selected and callable(lookup):
                        cost_flow_manager.set_official_efficiencies(scope_id, lookup(*selected))
                        # The selection reply is intentionally rendered only after
                        # the authoritative profile has enriched the full vehicle object.
                        result = mileage_confirmation + cost_flow_manager.vehicle_selection_reply(scope_id)
                followup = cost_flow_manager.pop_followup(scope_id)
                if followup:
                    self._persist_cost_calculation(scope_id)
                    if hasattr(self._line_client, "reply_flex"):
                        self._line_client.reply_flex(reply_token, build_cost_result_flex(result, cost_flow_manager.calculation_id(scope_id), source_type))
                        self._line_client.reply_text(reply_token, followup)
                    else:
                        self._line_client.reply_texts(reply_token, [result, followup])
                else:
                    if cost_flow_manager.current_stage(scope_id) == "full_cost_result" and hasattr(self._line_client, "reply_flex"):
                        self._persist_cost_calculation(scope_id)
                        self._line_client.reply_flex(reply_token, build_full_cost_result_flex(result, cost_flow_manager.calculation_id(scope_id)))
                        continue
                    # Once a powertrain is chosen, use Supabase-backed Flex cards
                    # instead of listing models as plain text.
                    if self._repository and cost_flow_manager.current_stage(scope_id) in {"vehicle_model", "vehicle_b_model"}:
                        list_profiles = getattr(self._repository, "list_active_vehicle_profiles_by_powertrain", None)
                        pending = cost_flow_manager._states[scope_id].values.get("pending_powertrain")
                        vehicles = list_profiles(str(pending)) if callable(list_profiles) else []
                        if vehicles and hasattr(self._line_client, "reply_flex"):
                            slot = "A" if cost_flow_manager.current_stage(scope_id) == "vehicle_model" else "B"
                            self._line_client.reply_flex(reply_token, build_vehicle_carousel(vehicles, slot))
                        else:
                            self._reply_cost_flow(reply_token, scope_id, result)
                    else:
                        self._reply_cost_flow(reply_token, scope_id, result)
                continue
            comparison_response = comparison_context_manager.respond(scope_id, message_text)
            if comparison_response:
                decision, context = comparison_response
                if decision == "declined":
                    self._line_client.reply_text(reply_token, "沒問題，需要時再叫我一起比較就好。")
                elif context:
                    self._line_client.reply_text(
                        reply_token,
                        self._start_comparison_cost_flow(scope_id, context.current_drivetrain, source),
                    )
                continue
            vehicle_reply = self._matched_vehicle_reply(message_text, source_type, source.get("userId", ""))
            if vehicle_reply:
                self._record_vehicle_entities(scope_id, source, message_text)
                profiles = find_vehicles_in_text(message_text, self._repository.list_active_vehicle_profiles()) if self._repository else []
                comparison_context_manager.offer(scope_id, profiles)
                self._line_client.reply_text(reply_token, vehicle_reply)
                continue

            routed_reply = route_text_message(message_text, source_type)
            if not routed_reply:
                if source_type == "user" and any(token in message_text.lower() for token in ("電車", "電動車", "ev", "電池", "toyota", "豐田")):
                    if "不確定要不要買" in message_text or "還沒決定" in message_text:
                        self._line_client.reply_text(reply_token, "沒關係，可以先不用決定。若你願意，我可以先從里程、充電條件和用車需求，陪你看看純電車適不適合。")
                    elif message_text.strip() in {"電車", "電動車", "ev"}:
                        self._line_client.reply_text(reply_token, "你想了解電動車哪一部分？可以問我充電、電池、續航、成本，或直接說你正在考慮什麼。")
                    else:
                        self._line_client.reply_text(reply_token, "這題我可以幫你查官方資料；你也可以補充想問的車款或使用情境。")
                continue
            self._reply_routed_faq(reply_token, source, routed_reply, message_text)


event_processor = EventProcessor()
