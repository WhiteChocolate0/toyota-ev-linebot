"""Read-only access to shared official reference data.

This repository deliberately owns no LINE conversation state and performs no
normal-chat writes.  The campaign website and LINE bot therefore read the same
catalogue, sources, tax rules, and energy references from ``public``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from supabase import Client

from app.services.powertrain import normalize_powertrain

logger = logging.getLogger(__name__)


class SharedReferenceRepository:
    database_area = "shared"

    def __init__(self, client: Client) -> None:
        self._client = client.schema("public")

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    def get_knowledge_source(self, source_id: str) -> dict | None:
        try:
            response = self._client.table("knowledge_sources").select(
                "publisher,title,url,content,source_type,verified_at,valid_until"
            ).eq("id", source_id).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").limit(1).execute()
            row = response.data[0] if response.data else None
            if row and str(row.get("source_type", "")).casefold() in {"official", "public_official", "government", "manufacturer", "owner_manual", "toyota_official"}:
                return row
            return None
        except Exception:
            logger.warning("Shared knowledge source lookup failed", extra={"database_area": self.database_area})
            return None

    def search_knowledge_sources(self, *, query: str, topic: str | None, terms: tuple[str, ...]) -> list[dict]:
        try:
            response = self._client.table("knowledge_sources").select(
                "id,category,topic,publisher,title,content,url,source_type,verified_at,valid_until,vehicle_scope,country_scope,keywords,is_active,priority"
            ).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").limit(100).execute()
            rows = response.data or []
            return [row for row in rows if str(row.get("source_type", "")).casefold() in {"official", "public_official", "government", "manufacturer", "owner_manual", "toyota_official"}]
        except Exception:
            logger.warning("Shared knowledge search failed", extra={"database_area": self.database_area})
            return []

    def get_today_reference_parameter(self, parameter_key: str) -> dict | None:
        taipei = ZoneInfo("Asia/Taipei")
        start = datetime.now(taipei).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        try:
            response = self._client.table("reference_parameters").select(
                "value_numeric,effective_date,source_url,fetched_at,verified_at,valid_until,source_type"
            ).eq("parameter_key", parameter_key).gte("fetched_at", start.isoformat()).order("fetched_at", desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Shared energy reference lookup failed", extra={"database_area": self.database_area})
            return None

    def get_latest_reference_parameter(self, parameter_key: str) -> dict | None:
        try:
            response = self._client.table("reference_parameters").select(
                "value_numeric,effective_date,source_url,fetched_at,verified_at,valid_until,source_type"
            ).eq("parameter_key", parameter_key).order("fetched_at", desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Shared energy reference fallback lookup failed", extra={"database_area": self.database_area})
            return None

    def list_active_vehicle_profiles(self) -> list[dict]:
        try:
            response = self._client.table("vehicle_profiles").select(
                "id,model_name,model_year,trim_name,drivetrain,aliases,purchase_price_ntd,energy_efficiency,seats,cargo_capacity_l,cargo_notes,body_type,length_mm,width_mm,height_mm,wheelbase_mm,source_url,verified_at,valid_until,vehicle_specifications(official_range_km,charging_requirement,warranty_json,verified_at,valid_until,is_active)"
            ).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").execute()
            return [self._merge_active_specification(row) for row in response.data or []]
        except Exception:
            logger.warning("Shared vehicle catalogue lookup failed", extra={"database_area": self.database_area})
            return []

    @staticmethod
    def _merge_active_specification(profile: dict) -> dict:
        rows = profile.pop("vehicle_specifications", []) or []
        valid = [row for row in rows if row.get("is_active") and (not row.get("valid_until") or row["valid_until"] >= datetime.now(UTC).isoformat())]
        if valid:
            spec = sorted(valid, key=lambda row: str(row.get("verified_at", "")), reverse=True)[0]
            profile.update(range_km=spec.get("official_range_km"), charging_requirement=spec.get("charging_requirement"), warranty=spec.get("warranty_json"))
        return profile

    def list_recommendation_profiles(self) -> list[dict]:
        return self.list_active_vehicle_profiles()

    def get_active_vehicle_energy_profile(self, model_name: str, drivetrain: str) -> dict | None:
        normalized = normalize_powertrain(drivetrain) or drivetrain
        rows = [row for row in self.list_active_vehicle_profiles() if row.get("model_name", "").casefold() == model_name.casefold() and normalize_powertrain(str(row.get("drivetrain", ""))) == normalized]
        return rows[0] if rows else None

    def list_active_vehicle_profiles_by_powertrain(self, drivetrain: str) -> list[dict]:
        normalized = normalize_powertrain(drivetrain) or drivetrain
        return [row for row in self.list_active_vehicle_profiles() if normalize_powertrain(str(row.get("drivetrain", ""))) == normalized]

    def get_active_vehicle_profile_by_id(self, vehicle_id: str) -> dict | None:
        try:
            response = self._client.table("vehicle_profiles").select(
                "id,model_name,trim_name,drivetrain,purchase_price_ntd,fuel_efficiency_km_per_l,electric_efficiency_km_per_kwh,energy_efficiency,energy_efficiency_unit,source_url,verified_at,valid_until"
            ).eq("id", vehicle_id).eq("is_active", True).or_(f"valid_until.is.null,valid_until.gte.{self.now()}").limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Shared vehicle lookup failed", extra={"database_area": self.database_area})
            return None

    def get_vehicle_feature(self, model_name: str, feature_code: str) -> dict | None:
        try:
            response = self._client.table("vehicle_features").select(
                "model_name,feature_code,description,source_type,source_url,verified_at,valid_until"
            ).ilike("model_name", model_name).eq("feature_code", feature_code).eq("source_type", "official").or_(f"valid_until.is.null,valid_until.gte.{self.now()}").order("verified_at", desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception:
            logger.warning("Shared vehicle feature lookup failed", extra={"database_area": self.database_area})
            return None

    def get_tax_rules(self) -> list[dict]:
        return self._active_rows("tax_rules", "effective_to")

    def get_energy_prices(self) -> list[dict]:
        return self._active_rows("energy_prices", "effective_to")

    def _active_rows(self, table: str, expiry_column: str) -> list[dict]:
        try:
            response = self._client.table(table).select("*").or_(f"{expiry_column}.is.null,{expiry_column}.gte.{datetime.now(UTC).date().isoformat()}").execute()
            return response.data or []
        except Exception:
            logger.warning("Shared reference lookup failed", extra={"database_area": self.database_area, "table": table})
            return []
