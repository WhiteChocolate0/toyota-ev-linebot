"""LINE Bot persistence boundary with an explicit legacy-schema contract."""

from __future__ import annotations

import hashlib
import logging

from supabase import Client, create_client

from app.config import get_settings
from app.services.environment_safety import EnvironmentSafetyError, validate_database_environment
from app.services.campaign_handoff import normalize_campaign_rpc_result
from app.services.shared_reference_repository import SharedReferenceRepository
from app.services.supabase_repository import SupabaseRepository

logger = logging.getLogger(__name__)

_SHARED_TABLES = {"vehicle_profiles", "vehicle_specifications", "vehicle_features", "knowledge_sources", "tax_rules", "energy_prices", "reference_parameters"}
_INTERNAL_TABLES = {
    "internal_research_sources", "internal_concern_priorities",
    "internal_vehicle_alias_mappings", "internal_vehicle_service_benchmarks",
}


class _AreaClient:
    """Compatibility adapter while state methods are progressively extracted."""
    def __init__(self, client: Client, state_schema: str) -> None:
        self._client = client
        self._state_schema = state_schema

    def table(self, name: str):
        area = "public" if name in _SHARED_TABLES or name in _INTERNAL_TABLES else self._state_schema
        return self._client.schema(area).table(name)


class LinebotRepository(SupabaseRepository):
    database_area = "public_legacy"

    def __init__(self) -> None:
        settings = get_settings()
        validate_database_environment(settings, operation="LINE Bot runtime")
        state_schema = settings.bot_state_schema.strip().casefold()
        if state_schema not in {"public", "linebot"}:
            raise ValueError("BOT_STATE_SCHEMA must be public or linebot")
        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        self._client = _AreaClient(client, state_schema)
        self.database_area = state_schema
        self.shared = SharedReferenceRepository(client)

    # Shared reads are explicit delegation; this repository never writes them.
    get_knowledge_source = lambda self, *a, **kw: self.shared.get_knowledge_source(*a, **kw)
    search_knowledge_sources = lambda self, *a, **kw: self.shared.search_knowledge_sources(*a, **kw)
    get_today_reference_parameter = lambda self, *a, **kw: self.shared.get_today_reference_parameter(*a, **kw)
    get_latest_reference_parameter = lambda self, *a, **kw: self.shared.get_latest_reference_parameter(*a, **kw)
    list_active_vehicle_profiles = lambda self, *a, **kw: self.shared.list_active_vehicle_profiles(*a, **kw)
    list_recommendation_profiles = lambda self, *a, **kw: self.shared.list_recommendation_profiles(*a, **kw)
    get_active_vehicle_energy_profile = lambda self, *a, **kw: self.shared.get_active_vehicle_energy_profile(*a, **kw)
    list_active_vehicle_profiles_by_powertrain = lambda self, *a, **kw: self.shared.list_active_vehicle_profiles_by_powertrain(*a, **kw)
    get_active_vehicle_profile_by_id = lambda self, *a, **kw: self.shared.get_active_vehicle_profile_by_id(*a, **kw)
    get_vehicle_feature = lambda self, *a, **kw: self.shared.get_vehicle_feature(*a, **kw)

    def save_reference_parameter(self, **_record: object) -> None:
        # Official references are admin/migration managed, never mutated by chat.
        logger.info("Skipped shared reference write from LINE chat", extra={"database_area": "shared"})

    def consume_campaign_token(self, token: str, _line_user_id: str = "") -> dict:
        """Use the DB RPC so validation, consumption, and handoff are atomic."""
        try:
            response = self._client._client.rpc("consume_campaign_handoff", {
                # The bearer token never crosses the RPC boundary; Postgres
                # receives only the hash stored in campaign.link_tokens.
                "p_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            }).execute()
            data = response.data
            if isinstance(data, dict):
                return normalize_campaign_rpc_result(data)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return normalize_campaign_rpc_result(data[0])
            return {"status": "HANDOFF_UNAVAILABLE"}
        except Exception:
            logger.warning("Campaign handoff failed", extra={"database_area": "campaign"}, exc_info=True)
            return {"status": "HANDOFF_UNAVAILABLE"}

    def list_internal_concern_priorities(self, limit: int = 11) -> list[dict]:
        try:
            response = self._client.table("internal_concern_priorities").select(
                "id,concern_type,priority_rank,weight,research_source_id,snapshot_period,visibility,created_at"
            ).eq("visibility", "INTERNAL_ORGANIZER").order("priority_rank").limit(min(max(limit, 0), 50)).execute()
            return response.data or []
        except Exception:
            logger.warning("Internal concern priority lookup failed", extra={"database_area": "internal"}, exc_info=True)
            return []

    def get_internal_vehicle_service_benchmark(self, vehicle_id: str, vehicle_age_bucket: str) -> dict | None:
        try:
            response = self._client.table("internal_vehicle_service_benchmarks").select("*").eq(
                "vehicle_id", vehicle_id
            ).eq("vehicle_age_bucket", vehicle_age_bucket).eq("visibility", "INTERNAL_ORGANIZER").limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Internal service benchmark lookup failed", extra={"database_area": "internal"}, exc_info=True)
            return None

    def list_internal_vehicle_age_distribution(self, vehicle_id: str) -> list[dict]:
        try:
            response = self._client.table("internal_vehicle_service_benchmarks").select(
                "vehicle_age_bucket,sample_size"
            ).eq("vehicle_id", vehicle_id).eq("visibility", "INTERNAL_ORGANIZER").order("vehicle_age_bucket").execute()
            return response.data or []
        except Exception:
            logger.warning("Internal age-cohort lookup failed", extra={"database_area": "internal"}, exc_info=True)
            return []


def get_repository() -> LinebotRepository | None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    try:
        return LinebotRepository()
    except EnvironmentSafetyError:
        # Fail closed: application may use its existing in-memory/fake paths,
        # but this process receives no database client.
        logger.critical("Database repository disabled by environment safety guard", exc_info=True)
        return None
