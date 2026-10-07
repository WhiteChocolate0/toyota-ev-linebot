"""Minimal, privacy-preserving persistence for webhook, group, and knowledge metadata."""

import hashlib
import logging
from datetime import UTC, datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from supabase import Client, create_client

from app.config import get_settings
from app.services.environment_safety import validate_database_environment
from app.services.powertrain import normalize_powertrain
from app.services.group_intelligence import topic_name

logger = logging.getLogger(__name__)


class SupabaseRepository:
    def __init__(self) -> None:
        settings = get_settings()
        validate_database_environment(settings, operation="LINE Bot runtime")
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    @staticmethod
    def hash_line_group_id(line_group_id: str) -> str:
        return hashlib.sha256(line_group_id.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_line_user_id(line_user_id: str) -> str:
        return hashlib.sha256(line_user_id.encode("utf-8")).hexdigest()

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    def conversation_scope_key(self, group_id: str | None, line_user_id: str) -> str:
        """Stable DB scope for either a private chat or one group member.

        Do not use a nullable group id in a uniqueness boundary: PostgreSQL
        treats NULLs as distinct and would otherwise create duplicate private
        contexts/flows after cold starts.
        """
        user_hash = self.hash_line_user_id(line_user_id)
        return f"group:{group_id}:user:{user_hash}" if group_id else f"private:{user_hash}"

    def claim_event(self, event_id: str) -> bool | None:
        try:
            self._client.table("webhook_events").insert({"event_id": event_id}).execute()
            return True
        except Exception as exc:
            if getattr(exc, "code", None) == "23505":
                return False
            logger.warning("Webhook event was not persisted; using in-memory fallback", exc_info=True)
            return None

    def touch_group(self, line_group_id: str) -> str | None:
        try:
            response = self._client.table("groups").upsert(
                {"line_group_id_hash": self.hash_line_group_id(line_group_id), "status": "active", "last_active_at": self.now()},
                on_conflict="line_group_id_hash",
            ).execute()
            return response.data[0]["id"] if response.data else None
        except Exception:
            logger.warning("Group metadata was not persisted", exc_info=True)
            return None

    def member_needs_onboarding(self, group_id: str, line_user_id: str) -> bool:
        """Register a real Bot interaction and return its one-time onboarding state."""
        if not line_user_id:
            return False
        try:
            user_hash = self.hash_line_user_id(line_user_id)
            response = self._client.table("group_member_bot_profiles").select(
                "has_seen_onboarding"
            ).eq("group_id", group_id).eq("user_id_hash", user_hash).limit(1).execute()
            now = self.now()
            if response.data:
                self._client.table("group_member_bot_profiles").update({
                    "last_interaction_at": now, "updated_at": now
                }).eq("group_id", group_id).eq("user_id_hash", user_hash).execute()
                return not bool(response.data[0]["has_seen_onboarding"])
            self._client.table("group_member_bot_profiles").insert({
                "group_id": group_id, "user_id_hash": user_hash,
                "first_interaction_at": now, "last_interaction_at": now,
            }).execute()
            return True
        except Exception:
            logger.warning("Member onboarding profile was not persisted", exc_info=True)
            return False

    def mark_member_onboarded(self, group_id: str, line_user_id: str) -> None:
        if not line_user_id:
            return
        try:
            now = self.now()
            self._client.table("group_member_bot_profiles").update({
                "has_seen_onboarding": True, "last_interaction_at": now, "updated_at": now
            }).eq("group_id", group_id).eq("user_id_hash", self.hash_line_user_id(line_user_id)).execute()
        except Exception:
            logger.warning("Member onboarding state was not updated", exc_info=True)

    def record_concern(self, group_id: str, concern_type: str) -> None:
        if concern_type in {"unknown", "unrelated"}:
            return
        try:
            self._client.table("concerns").upsert(
                {"group_id": group_id, "concern_type": concern_type, "last_seen": self.now()},
                on_conflict="group_id,concern_type",
            ).execute()
            self._client.table("conversation_events").insert(
                {"group_id": group_id, "message_type": "text", "intent": concern_type,
                 "concern_type": concern_type, "relevance_score": 1.0,
                 "summary": f"Detected concern: {concern_type}"}
            ).execute()
        except Exception:
            logger.warning("Concern metadata was not persisted", exc_info=True)

    def record_group_signal(self, group_id: str, line_user_id: str, topic: str, stance: str, labels: tuple[str, ...]) -> bool:
        """Store bounded EV metadata only; returns whether a gentle summary offer is due."""
        if topic in {"UNRELATED", "unknown", "unrelated"}:
            return False
        try:
            now = datetime.now(UTC)
            self._client.table("concerns").upsert(
                {"group_id": group_id, "concern_type": topic, "last_seen": now.isoformat()},
                on_conflict="group_id,concern_type",
            ).execute()
            self._client.table("conversation_events").insert({
                "group_id": group_id, "message_type": "group_signal", "intent": topic,
                "concern_type": topic, "relevance_score": 1.0,
                "summary": f"EV discussion: {topic_name(topic)} ({stance})",
            }).execute()
            if line_user_id:
                expiry = (now + timedelta(days=100)).isoformat()
                for label in labels:
                    self._client.table("group_member_signals").upsert({
                        "group_id": group_id, "member_id_hash": self.hash_line_user_id(line_user_id),
                        "label": label, "weight": 1, "expires_at": expiry, "updated_at": now.isoformat(),
                    }, on_conflict="group_id,member_id_hash,label").execute()
            group = self._client.table("groups").select("last_summary_offer_at,summary_opt_out_until").eq("id", group_id).limit(1).execute()
            row = (group.data or [{}])[0]
            if row.get("summary_opt_out_until") and row["summary_opt_out_until"] > now.isoformat():
                return False
            recent = self._client.table("conversation_events").select("id").eq("group_id", group_id).gte(
                "created_at", (now - timedelta(hours=24)).isoformat()
            ).limit(3).execute()
            last_offer = row.get("last_summary_offer_at")
            due = len(recent.data or []) >= 3 and (not last_offer or last_offer < (now - timedelta(hours=24)).isoformat())
            if due:
                self._client.table("groups").update({"last_summary_offer_at": now.isoformat()}).eq("id", group_id).execute()
            return due
        except Exception:
            logger.warning("Group discussion metadata was not persisted", exc_info=True)
            return False

    def update_concern_board(self, group_id: str, concern_type: str, status: str) -> None:
        """Store only bounded issue metadata; no people, claims or message text."""
        try:
            now = datetime.now(UTC)
            self._client.table("group_concern_board").upsert({
                "group_id": group_id, "concern_type": concern_type, "status": status,
                "evidence_count": 1, "last_updated": now.isoformat(), "expires_at": (now + timedelta(days=100)).isoformat(),
            }, on_conflict="group_id,concern_type").execute()
        except Exception:
            logger.warning("Concern board was not updated", exc_info=True)

    def concern_board(self, group_id: str) -> list[dict]:
        try:
            return self._client.table("group_concern_board").select("concern_type,status,evidence_count,last_updated,expires_at").eq("group_id", group_id).gte("expires_at", self.now()).order("last_updated", desc=True).execute().data or []
        except Exception:
            logger.warning("Concern board was not available", exc_info=True); return []

    def set_concern_board_status(self, group_id: str, concern_type: str, status: str) -> None:
        try:
            self._client.table("group_concern_board").update({"status": status, "last_updated": self.now()}).eq("group_id", group_id).eq("concern_type", concern_type).execute()
        except Exception:
            logger.warning("Concern board status was not updated", exc_info=True)

    def group_summary(self, group_id: str) -> str:
        """Create a short, source-free summary from persisted topic metadata."""
        try:
            rows = self._client.table("concerns").select("concern_type,status").eq("group_id", group_id).order("last_seen", desc=True).limit(6).execute().data or []
            open_topics = [topic_name(str(row["concern_type"])) for row in rows if row.get("status") == "open"]
            resolved = [topic_name(str(row["concern_type"])) for row in rows if row.get("status") == "resolved"]
            pending = "、".join(open_topics[:2]) or "目前尚未留下需確認的 EV 條件"
            clarified = "、".join(resolved[:2]) or "尚無標記為已釐清的項目"
            next_step = "確認住家充電條件" if any("充電" in item for item in open_topics) else "補齊用車里程後進行成本試算"
            payload = {"clarified": clarified, "pending": pending, "differences": "以資料確認為主，不替任何成員判定對錯", "next_step": next_step}
            self._client.table("group_summaries").insert({"group_id": group_id, "summary_json": payload}).execute()
            return f"今天的家庭 EV 討論\n✅ 已釐清：{clarified}\n🤔 待確認：{pending}\n⚖️ 尚有分歧：以資料確認為主，不替任何成員判定對錯\n👉 下一步：{next_step}"
        except Exception:
            logger.warning("Group summary was not available", exc_info=True)
            return "目前還沒有足夠的 EV 討論重點可整理；可先從充電條件、日常里程或成本試算開始。"

    def clear_group_summary(self, group_id: str, *, delete: bool = False) -> str:
        try:
            if delete:
                self._client.table("group_summaries").update({"deleted_at": self.now()}).eq("group_id", group_id).is_("deleted_at", "null").execute()
                self._client.table("conversation_events").delete().eq("group_id", group_id).eq("message_type", "group_signal").execute()
                return "已刪除群組 EV 討論摘要與短期討論記憶；不影響成本試算紀錄。"
            self._client.table("groups").update({"summary_opt_out_until": (datetime.now(UTC) + timedelta(days=7)).isoformat()}).eq("id", group_id).execute()
            return "已重設摘要建議；接下來 7 天不會主動詢問是否整理。"
        except Exception:
            logger.warning("Group summary reset failed", exc_info=True)
            return "目前無法更新摘要設定，請稍後再試。"

    def save_conversation_flow(self, group_id: str | None, owner_user_id: str, snapshot: dict[str, object], *, flow_type: str = "cost_calculation") -> bool:
        try:
            scope_key = self.conversation_scope_key(group_id, owner_user_id)
            status = str(snapshot.get("status", "active"))
            self._client.table("conversation_flows").upsert(
                {"group_id": group_id, "scope_key": scope_key, "owner_user_id_hash": self.hash_line_user_id(owner_user_id),
                 "flow_type": flow_type, "current_state": snapshot.get("current_state") if status == "active" else None,
                 "pending_field": snapshot.get("pending_field") if status == "active" else None, "status": status, "updated_at": self.now()},
                on_conflict="scope_key,flow_type",
            ).execute()
            return True
        except Exception:
            logger.warning("Conversation flow was not persisted", exc_info=True)
            return False

    def get_active_conversation_flow(self, group_id: str | None, owner_user_id: str, flow_type: str) -> dict | None:
        try:
            response = self._client.table("conversation_flows").select("*").eq(
                "scope_key", self.conversation_scope_key(group_id, owner_user_id)
            ).eq("flow_type", flow_type).in_("status", ["active", "paused"]).or_(f"expires_at.is.null,expires_at.gte.{self.now()}").limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Conversation flow lookup failed", exc_info=True)
            return None

    def cancel_conversation_flow(self, group_id: str | None, owner_user_id: str, flow_type: str) -> bool:
        try:
            self._client.table("conversation_flows").update({"status": "cancelled", "current_state": None, "pending_field": None, "updated_at": self.now()}).eq(
                "scope_key", self.conversation_scope_key(group_id, owner_user_id)
            ).eq("flow_type", flow_type).execute()
            return True
        except Exception:
            logger.warning("Conversation flow cancellation was not persisted", exc_info=True)
            return False

    def cancel_active_conversation_flows(self, group_id: str | None, owner_user_id: str) -> bool:
        """One cancellation path for text commands and postback controls."""
        try:
            self._client.table("conversation_flows").update({"status": "cancelled", "current_state": None, "pending_field": None, "updated_at": self.now()}).eq(
                "scope_key", self.conversation_scope_key(group_id, owner_user_id)
            ).in_("status", ["active", "paused"]).execute()
            return True
        except Exception:
            logger.warning("Active flow cancellation was not persisted", exc_info=True)
            return False

    def get_knowledge_source(self, source_id: str) -> dict | None:
        try:
            response = self._client.table("knowledge_sources").select(
                "publisher,title,url,content,verified_at,valid_until"
            ).eq("id", source_id).or_(
                f"valid_until.is.null,valid_until.gte.{self.now()}"
            ).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Knowledge source lookup failed", exc_info=True)
            return None

    def search_knowledge_sources(self, *, query: str, topic: str | None, terms: tuple[str, ...]) -> list[dict]:
        """Candidate pool for Hybrid RAG; reranking remains in the service."""
        try:
            response = self._client.table("knowledge_sources").select(
                "id,category,topic,publisher,title,content,url,source_type,verified_at,valid_until,vehicle_scope,country_scope,keywords,is_active,priority"
            ).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").limit(100).execute()
            return response.data or []
        except Exception:
            logger.warning("Hybrid knowledge search failed", exc_info=True)
            return []

    def record_knowledge_gap(self, query_hash: str, topic: str | None, retrieval_score: float | None) -> None:
        try:
            self._client.table("knowledge_gap_logs").insert({
                "query_hash": query_hash, "topic": topic, "retrieval_score": retrieval_score,
            }).execute()
        except Exception:
            logger.warning("Knowledge gap was not recorded", exc_info=True)

    def get_today_reference_parameter(self, parameter_key: str) -> dict | None:
        """Return a value fetched since the start of today in Taiwan time."""
        taipei = ZoneInfo("Asia/Taipei")
        today_start = datetime.now(taipei).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        try:
            response = self._client.table("reference_parameters").select(
                "value_numeric,effective_date,source_url,fetched_at"
            ).eq("parameter_key", parameter_key).gte("fetched_at", today_start.isoformat()).order(
                "fetched_at", desc=True
            ).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Today reference-parameter cache lookup failed", exc_info=True)
            return None

    def get_latest_reference_parameter(self, parameter_key: str) -> dict | None:
        try:
            response = self._client.table("reference_parameters").select(
                "value_numeric,effective_date,source_url,fetched_at"
            ).eq("parameter_key", parameter_key).order("fetched_at", desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Reference-parameter fallback lookup failed", exc_info=True)
            return None

    def save_reference_parameter(
        self,
        *,
        parameter_key: str,
        value_numeric: float,
        effective_date: str,
        source_url: str,
    ) -> None:
        try:
            self._client.table("reference_parameters").upsert(
                {
                    "parameter_key": parameter_key,
                    "value_numeric": value_numeric,
                    "effective_date": effective_date,
                    "source_url": source_url,
                    "fetched_at": self.now(),
                },
                on_conflict="parameter_key,effective_date",
            ).execute()
        except Exception:
            logger.warning("Reference-parameter cache write failed", exc_info=True)

    def list_active_vehicle_profiles(self) -> list[dict]:
        """Return only catalog entries whose source freshness has not expired."""
        try:
            response = self._client.table("vehicle_profiles").select(
                "id,model_name,model_year,trim_name,drivetrain,aliases,purchase_price_ntd,energy_efficiency,seats,cargo_capacity_l,cargo_notes,body_type,length_mm,width_mm,height_mm,wheelbase_mm,source_url,verified_at,valid_until,vehicle_specifications(official_range_km,charging_requirement,warranty_json,verified_at,valid_until,is_active)"
            ).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").execute()
            return [self._merge_active_specification(row) for row in response.data or []]
        except Exception:
            logger.warning("Vehicle catalog lookup failed", exc_info=True)
            return []

    @staticmethod
    def _merge_active_specification(profile: dict) -> dict:
        """Flatten the newest valid specification without overwriting catalogue facts."""
        rows = profile.pop("vehicle_specifications", []) or []
        valid = [row for row in rows if row.get("is_active") and (not row.get("valid_until") or row["valid_until"] >= datetime.now(UTC).isoformat())]
        if not valid:
            return profile
        spec = sorted(valid, key=lambda row: str(row.get("verified_at", "")), reverse=True)[0]
        profile["range_km"] = spec.get("official_range_km")
        profile["charging_requirement"] = spec.get("charging_requirement")
        profile["warranty"] = spec.get("warranty_json")
        return profile

    def list_recommendation_profiles(self) -> list[dict]:
        """Verified catalog fields only; null remains unknown to the recommender."""
        try:
            response = self._client.table("vehicle_profiles").select(
                "id,model_name,trim_name,drivetrain,purchase_price_ntd,seats,cargo_capacity_l,cargo_notes,rear_seat_foldable,body_type,source_url,verified_at"
            ).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").execute()
            return response.data or []
        except Exception:
            logger.warning("Recommendation catalog lookup failed", exc_info=True)
            return []

    def save_vehicle_preference_profile(self, group_id: str, line_user_id: str, profile: dict) -> None:
        if not line_user_id:
            return
        try:
            self._client.table("vehicle_preference_profiles").upsert({
                "group_id": group_id, "user_id_hash": self.hash_line_user_id(line_user_id),
                "profile_json": profile, "updated_at": self.now(),
            }, on_conflict="group_id,user_id_hash").execute()
        except Exception:
            logger.warning("Vehicle preference profile was not persisted", exc_info=True)

    def get_conversation_context(self, group_id: str | None, line_user_id: str) -> dict | None:
        """Return one user's unexpired structured context; never message text."""
        if not line_user_id:
            return None
        try:
            response = self._client.table("conversation_contexts").select(
                "context_json,updated_at,expires_at"
            ).eq("scope_key", self.conversation_scope_key(group_id, line_user_id)).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Conversation context lookup failed", exc_info=True)
            return None

    def save_conversation_context(self, group_id: str | None, line_user_id: str, context: dict, expires_at: str) -> bool:
        """Persist only short-lived structured context, never the source message."""
        if not line_user_id:
            return False
        try:
            self._client.table("conversation_contexts").upsert({
                "group_id": group_id, "scope_key": self.conversation_scope_key(group_id, line_user_id), "user_id_hash": self.hash_line_user_id(line_user_id),
                "context_json": context, "updated_at": self.now(), "expires_at": expires_at,
            }, on_conflict="scope_key").execute()
            return True
        except Exception:
            logger.warning("Conversation context was not persisted", exc_info=True)
            return False

    def get_active_vehicle_energy_profile(self, model_name: str, drivetrain: str) -> dict | None:
        """One verified official profile for prefilling (never an expired value)."""
        try:
            response = self._client.table("vehicle_profiles").select(
                "id,model_name,trim_name,drivetrain,purchase_price_ntd,fuel_efficiency_km_per_l,electric_efficiency_km_per_kwh,source_url,verified_at"
            ).eq("is_active", True).ilike("model_name", model_name).or_(
                f"valid_until.is.null,valid_until.gte.{self.now()}"
            ).order("verified_at", desc=True).limit(10).execute()
            target_powertrain = normalize_powertrain(drivetrain)
            matching_profiles = []
            for profile in response.data or []:
                if normalize_powertrain(str(profile.get("drivetrain", ""))) == target_powertrain:
                    matching_profiles.append(profile)
            # When a family name has several trims but the user has not selected one,
            # prefer the ordinary trim over a special edition as the documented default.
            matching_profiles.sort(key=lambda item: ("豪華" not in str(item.get("trim_name", "")), "選" in str(item.get("trim_name", ""))))
            return matching_profiles[0] if matching_profiles else None
        except Exception:
            logger.warning("Official vehicle energy-profile lookup failed", exc_info=True)
            return None

    def list_active_vehicle_profiles_by_powertrain(self, drivetrain: str) -> list[dict]:
        """Catalog data for Flex selection; all choices remain server-authoritative."""
        try:
            response = self._client.table("vehicle_profiles").select(
                "id,model_name,trim_name,drivetrain,purchase_price_ntd,fuel_efficiency_km_per_l,electric_efficiency_km_per_kwh,energy_efficiency,energy_efficiency_unit,source_url"
            ).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").execute()
            target = normalize_powertrain(drivetrain)
            rows = [row for row in response.data or [] if normalize_powertrain(str(row.get("drivetrain", ""))) == target]
            return sorted(rows, key=lambda row: (row.get("purchase_price_ntd") is None, row.get("purchase_price_ntd") or 0, row["model_name"]))
        except Exception:
            logger.warning("Vehicle carousel catalog lookup failed", exc_info=True)
            return []

    def get_active_vehicle_profile_by_id(self, vehicle_id: str) -> dict | None:
        try:
            response = self._client.table("vehicle_profiles").select(
                "id,model_name,trim_name,drivetrain,purchase_price_ntd,fuel_efficiency_km_per_l,electric_efficiency_km_per_kwh,energy_efficiency,energy_efficiency_unit,source_url"
            ).eq("id", vehicle_id).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Vehicle profile-by-id lookup failed", exc_info=True)
            return None

    def get_vehicle_feature(self, model_name: str, feature_code: str) -> dict | None:
        """Return a verified, reusable product feature rather than prompt copy."""
        try:
            response = self._client.table("vehicle_features").select(
                "model_name,feature_code,description,source_type,source_url,verified_at"
            ).ilike("model_name", model_name).eq("feature_code", feature_code).eq(
                "source_type", "official"
            ).order("verified_at", desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Vehicle feature lookup failed", exc_info=True)
            return None

    def save_cost_calculation(self, snapshot: dict[str, object]) -> None:
        """Upsert one calculation by its stable ID, so edits never create duplicates."""
        try:
            monthly_mileage = snapshot.get("monthly_mileage")
            assumptions = snapshot.get("assumptions", {})
            current_result = snapshot.get("current_result", {})
            self._client.table("cost_calculations").upsert(
                {**snapshot,
                 # Compatibility payload for the original TCO schema (004).
                 "annual_mileage": float(monthly_mileage or 0) * 12,
                 "inputs_json": snapshot,
                 "assumptions_json": assumptions,
                 "result_json": current_result,
                 "updated_at": self.now()}, on_conflict="calculation_id"
            ).execute()
        except Exception:
            logger.warning("Cost calculation was not persisted", exc_info=True)

    def save_cost_scenario(self, scenario: dict[str, object]) -> None:
        if not scenario.get("parent_calculation_id"):
            logger.warning("Cost scenario skipped because it has no base calculation")
            return
        try:
            self._client.table("cost_scenarios").insert(scenario).execute()
        except Exception:
            logger.warning("Cost scenario was not persisted", exc_info=True)

    def save_recent_user_result(self, line_user_id: str, result_type: str, result_id: str, summary: dict) -> None:
        if not line_user_id: return
        try:
            now = datetime.now(UTC)
            self._client.table("recent_user_results").upsert({"user_id_hash": self.hash_line_user_id(line_user_id), "result_type": result_type, "result_id": result_id, "summary_json": summary, "completed_at": now.isoformat(), "expires_at": (now + timedelta(days=100)).isoformat()}, on_conflict="user_id_hash,result_type,result_id").execute()
        except Exception: logger.warning("Recent result was not persisted", exc_info=True)

    def recent_user_results(self, line_user_id: str) -> list[dict]:
        try:
            return self._client.table("recent_user_results").select("result_type,result_id,summary_json,completed_at").eq("user_id_hash", self.hash_line_user_id(line_user_id)).gte("expires_at", self.now()).order("completed_at", desc=True).limit(5).execute().data or []
        except Exception: logger.warning("Recent results unavailable", exc_info=True); return []

    def private_needs_onboarding(self, line_user_id: str) -> bool:
        try:
            response = self._client.table("private_user_bot_profiles").select("has_seen_private_menu").eq("user_id_hash", self.hash_line_user_id(line_user_id)).limit(1).execute()
            return not response.data or not response.data[0].get("has_seen_private_menu")
        except Exception: logger.warning("Private onboarding lookup failed", exc_info=True); return False

    def mark_private_onboarded(self, line_user_id: str) -> None:
        if not line_user_id: return
        try:
            now = self.now(); self._client.table("private_user_bot_profiles").upsert({"user_id_hash": self.hash_line_user_id(line_user_id), "has_seen_welcome": True, "has_seen_private_menu": True, "first_interaction_at": now, "last_interaction_at": now, "updated_at": now}, on_conflict="user_id_hash").execute()
        except Exception: logger.warning("Private onboarding update failed", exc_info=True)

    def get_cost_calculation(self, calculation_id: str) -> dict | None:
        try:
            response = self._client.table("cost_calculations").select("*").eq(
                "calculation_id", calculation_id
            ).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Cost calculation lookup failed", exc_info=True)
            return None

    def save_vehicle_comparison_session(self, group_id: str | None, line_user_id: str, vehicle_ids: list[str], dimensions: list[str], *, source_type: str) -> bool:
        if not (2 <= len(vehicle_ids) <= 3):
            return False
        try:
            now = datetime.now(UTC)
            self._client.table("vehicle_comparison_sessions").upsert({
                "group_id": group_id, "scope_key": self.conversation_scope_key(group_id, line_user_id),
                "owner_user_id_hash": self.hash_line_user_id(line_user_id), "vehicle_ids": vehicle_ids,
                "comparison_dimensions": dimensions, "source_type": source_type, "status": "active",
                "updated_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(),
            }, on_conflict="scope_key").execute()
            return True
        except Exception:
            logger.warning("Vehicle comparison session was not persisted", exc_info=True)
            return False

    def get_active_vehicle_comparison_session(self, group_id: str | None, line_user_id: str) -> dict | None:
        try:
            response = self._client.table("vehicle_comparison_sessions").select("*").eq(
                "scope_key", self.conversation_scope_key(group_id, line_user_id)
            ).eq("status", "active").gte("expires_at", self.now()).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Vehicle comparison session lookup failed", exc_info=True)
            return None

    def cancel_vehicle_comparison_session(self, group_id: str | None, line_user_id: str) -> bool:
        try:
            self._client.table("vehicle_comparison_sessions").update({"status": "cancelled", "updated_at": self.now()}).eq(
                "scope_key", self.conversation_scope_key(group_id, line_user_id)
            ).eq("status", "active").execute()
            return True
        except Exception:
            logger.warning("Vehicle comparison session cancellation was not persisted", exc_info=True)
            return False


def get_repository() -> SupabaseRepository | None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    return SupabaseRepository()
