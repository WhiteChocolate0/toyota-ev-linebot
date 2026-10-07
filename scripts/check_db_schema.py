#!/usr/bin/env python3
"""Read-only PostgREST schema audit for the configured Supabase project.

This check never writes rows. It validates exposed schemas/tables and the
repository's required columns through PostgREST OpenAPI and zero-row selects.
Postgres indexes/constraints are reported as UNKNOWN unless catalog metadata is
provided separately; PostgREST does not expose those guarantees.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings  # noqa: E402
from app.services.environment_safety import EnvironmentSafetyError, validate_database_environment  # noqa: E402


EXPECTED: dict[tuple[str, str], set[str]] = {
    ("campaign", "link_tokens"): {"id", "quiz_result_id", "token_hash", "status", "created_at", "expires_at", "consumed_at"},
    ("campaign", "quiz_sessions"): {"id", "anonymous_session_id", "started_at", "completed_at", "status", "created_at", "updated_at"},
    ("campaign", "quiz_answers"): {"id", "quiz_session_id", "question_id", "selected_option", "score_delta", "dimension_delta_json", "answered_at"},
    ("campaign", "quiz_results"): {"id", "quiz_session_id", "persona_key", "ability_scores_json", "result_summary", "created_at"},
    ("campaign", "share_results"): {"id", "quiz_result_id", "share_token_hash", "share_format", "created_at", "expires_at"},
    ("public", "conversation_contexts"): {"id", "scope_key", "group_id", "user_id_hash", "context_json", "updated_at", "expires_at"},
    ("public", "conversation_flows"): {"id", "scope_key", "group_id", "owner_user_id_hash", "flow_type", "current_state", "pending_field", "status", "expires_at", "updated_at"},
    ("public", "vehicle_preference_profiles"): {"id", "group_id", "user_id_hash", "profile_json", "updated_at"},
    ("public", "vehicle_comparison_sessions"): {"id", "scope_key", "group_id", "owner_user_id_hash", "vehicle_ids", "comparison_dimensions", "source_type", "status", "updated_at", "expires_at"},
    ("public", "cost_calculations"): {"calculation_id", "vehicle_a_id", "vehicle_b_id", "monthly_mileage", "annual_mileage", "ownership_years", "assumptions", "assumptions_json", "current_result", "result_json", "inputs_json", "updated_at"},
    ("public", "cost_scenarios"): {"id", "parent_calculation_id", "scenario_type", "override_json", "result_json", "created_at"},
    ("public", "recent_user_results"): {"id", "user_id_hash", "result_type", "result_id", "summary_json", "completed_at", "expires_at"},
    ("public", "group_member_bot_profiles"): {"id", "group_id", "user_id_hash", "has_seen_onboarding", "first_interaction_at", "last_interaction_at", "created_at", "updated_at"},
    ("public", "internal_concern_priorities"): {"id", "concern_type", "priority_rank", "weight", "research_source_id", "snapshot_period", "visibility", "created_at"},
    ("public", "internal_research_sources"): {"id", "title", "source_kind", "snapshot_period", "visibility", "created_at"},
    ("public", "internal_vehicle_alias_mappings"): {"id", "raw_model_name", "normalized_model_name", "vehicle_id", "mapping_status", "source_id", "snapshot_date", "visibility"},
    ("public", "internal_vehicle_service_benchmarks"): {"id", "vehicle_id", "vehicle_age_bucket", "sample_size", "avg_service_visits", "median_service_visits", "avg_paid_service_visits", "median_paid_service_visits", "avg_scheduled_maintenance_visits", "median_scheduled_maintenance_visits", "avg_repair_visits", "median_repair_visits", "avg_service_amount_a_currency", "median_service_amount_a_currency", "avg_maintenance_amount_a_currency", "median_maintenance_amount_a_currency", "source_id", "snapshot_date", "visibility", "currency_type", "status"},
    ("public", "vehicle_profiles"): {"id", "model_name", "model_year", "trim_name", "drivetrain", "purchase_price_ntd", "source_url", "verified_at", "valid_until", "is_active"},
    ("public", "knowledge_sources"): {"id", "category", "topic", "publisher", "title", "content", "url", "source_type", "verified_at", "valid_until", "is_active"},
    ("public", "tax_rules"): {"id", "rule_key", "rule_type", "vehicle_scope", "value_json", "effective_from", "effective_to", "source_id", "source_url", "source_type", "verified_at", "created_at", "updated_at"},
    ("public", "energy_prices"): {"id", "energy_type", "scenario_type", "price_value", "price_unit", "effective_from", "effective_to", "source_id", "source_url", "source_type", "verified_at", "created_at", "updated_at"},
}

REQUIRED_INDEXES: dict[tuple[str, str], set[str]] = {
    ("campaign", "link_tokens"): {"campaign_link_tokens_active_expiry_idx"},
    ("public", "tax_rules"): {"tax_rules_active_idx"},
    ("public", "energy_prices"): {"energy_prices_active_idx"},
    ("public", "internal_concern_priorities"): {"internal_concern_priorities_order_idx"},
    ("public", "internal_vehicle_alias_mappings"): {"internal_vehicle_alias_status_idx"},
    ("public", "internal_vehicle_service_benchmarks"): {"internal_benchmarks_vehicle_cohort_idx"},
}
REQUIRED_UNIQUE_COLUMNS: dict[tuple[str, str], set[tuple[str, ...]]] = {
    ("campaign", "link_tokens"): {("token_hash",)},
    ("public", "tax_rules"): {("rule_key",)},
    ("public", "internal_concern_priorities"): {("research_source_id", "concern_type", "snapshot_period")},
    ("public", "internal_vehicle_alias_mappings"): {("source_id", "raw_model_name", "snapshot_date")},
    ("public", "internal_vehicle_service_benchmarks"): {("vehicle_id", "vehicle_age_bucket", "source_id", "snapshot_date")},
}
REQUIRED_FOREIGN_KEYS: dict[tuple[str, str], set[tuple[str, str, str, str]]] = {
    ("campaign", "link_tokens"): {("quiz_result_id", "campaign", "quiz_results", "id")},
    ("public", "internal_concern_priorities"): {("research_source_id", "public", "internal_research_sources", "id")},
    ("public", "internal_vehicle_alias_mappings"): {("source_id", "public", "internal_research_sources", "id"), ("vehicle_id", "public", "vehicle_profiles", "id")},
    ("public", "internal_vehicle_service_benchmarks"): {("source_id", "public", "internal_research_sources", "id"), ("vehicle_id", "public", "vehicle_profiles", "id")},
}
RESTRICTED_TABLES = {
    ("campaign", "link_tokens"),
    ("public", "tax_rules"), ("public", "energy_prices"),
    ("public", "internal_research_sources"), ("public", "internal_concern_priorities"),
    ("public", "internal_vehicle_alias_mappings"), ("public", "internal_vehicle_service_benchmarks"),
}
CATALOG_REQUIRED_TABLES = (
    set(REQUIRED_INDEXES)
    | set(REQUIRED_UNIQUE_COLUMNS)
    | set(REQUIRED_FOREIGN_KEYS)
    | RESTRICTED_TABLES
)


def _schema_from_ref(document: dict[str, Any], ref: str) -> dict[str, Any]:
    node: Any = document
    for part in ref.removeprefix("#/").split("/"):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def _repository_table_references() -> dict[str, list[str]]:
    """Extract literal names and report the configured, not aspirational, route."""
    source = (ROOT / "app/services/supabase_repository.py").read_text(encoding="utf-8")
    names = sorted(set(re.findall(r'\.table\("([a-zA-Z0-9_]+)"\)', source)))
    router = (ROOT / "app/services/linebot_repository.py").read_text(encoding="utf-8")
    shared = set(re.findall(r'_SHARED_TABLES\s*=\s*\{([^}]+)\}', router, re.S)[0].replace('"', "").replace("'", "").replace("\n", "").replace(" ", "").split(","))
    state_schema = get_settings().bot_state_schema.strip().casefold() or "public"
    return {name: ["public" if name in shared else state_schema] for name in names}


def audit() -> dict[str, Any]:
    settings = get_settings()
    try:
        validate_database_environment(settings, operation="schema readiness check")
    except EnvironmentSafetyError as exc:
        return {"status": "BLOCKED", "error": str(exc), "tables": []}
    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_role_key
    if not url or not key:
        return {"status": "BLOCKED", "error": "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing", "tables": []}
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    client = httpx.Client(timeout=20)
    openapis: dict[str, dict[str, Any] | None] = {}
    try:
        response = client.get(f"{url}/rest/v1/", headers=headers)
        response.raise_for_status()
        openapis["public"] = response.json()
    except Exception as exc:
        return {"status": "BLOCKED", "error": f"Supabase PostgREST unavailable ({type(exc).__name__})", "tables": []}

    result: list[dict[str, Any]] = []
    for (schema, table), required in EXPECTED.items():
        if schema not in openapis:
            try:
                schema_doc = client.get(f"{url}/rest/v1/", headers={**headers, "Accept-Profile": schema})
                openapis[schema] = schema_doc.json() if schema_doc.status_code == 200 else None
            except Exception:
                openapis[schema] = None
        openapi = openapis.get(schema) or {}
        path = openapi.get("paths", {}).get(f"/{table}")
        definition = openapi.get("definitions", {}).get(table, {})
        actual: set[str] = set(definition.get("properties", {}).keys())
        actual_schema = schema if path is not None else None
        actual_table = table if path is not None else None
        legacy_public = False
        try:
            probe = client.get(f"{url}/rest/v1/{table}", headers={**headers, "Accept-Profile": schema}, params={"select": "*", "limit": "0"})
            payload = probe.json() if probe.content else None
            code = payload.get("code") if isinstance(payload, dict) else None
        except Exception as exc:
            probe, code = None, type(exc).__name__
        if probe is None or probe.status_code >= 500:
            status = "ERROR"
        elif probe.status_code == 406 and code == "PGRST106":
            status = "SCHEMA_NOT_EXPOSED"
        elif probe.status_code == 404 or code == "PGRST205":
            status = "MISSING"
        elif probe.status_code >= 400:
            status = "ERROR"
        else:
            status = "READY" if required <= actual else "PARTIAL"
        result.append({
            "schema": schema,
            "table": table,
            "actual_schema": actual_schema,
            "actual_table": actual_table,
            "status": status,
            "required_columns": sorted(required),
            "actual_columns": sorted(actual),
            "missing_columns": sorted(required - actual),
            "unexpected_columns": sorted(actual - required),
            "indexes": "UNKNOWN (requires Postgres catalog read)",
            "constraints": "UNKNOWN (requires Postgres catalog read)",
            "http_status": probe.status_code if probe is not None else None,
            "postgrest_code": code,
        })
    metadata_rpc = None
    metadata_error = None
    try:
        meta_response = client.post(f"{url}/rest/v1/rpc/dev_schema_contract", headers=headers, json={})
        if meta_response.status_code == 200:
            metadata_rpc = meta_response.json()
        else:
            metadata_error = f"HTTP {meta_response.status_code}"
    except Exception as exc:
        metadata_error = type(exc).__name__
    metadata_tables = {
        (row.get("schema"), row.get("table")): row
        for row in (metadata_rpc or {}).get("tables", [])
    }
    for item in result:
        key = (item["schema"], item["table"])
        metadata = metadata_tables.get(key)
        if not metadata_rpc:
            item["indexes"] = "UNKNOWN"
            item["constraints"] = "UNKNOWN"
            item["index_status"] = "NOT_VERIFIED"
            item["constraint_status"] = "NOT_VERIFIED"
            item["foreign_key_status"] = "NOT_VERIFIED"
            item["security_status"] = "NOT_VERIFIED"
            if key in CATALOG_REQUIRED_TABLES and item["status"] == "READY":
                item["status"] = "MISMATCH"
            continue
        indexes = metadata.get("indexes", []) if metadata else []
        actual_index_names = {index.get("name") for index in indexes if index.get("valid") and index.get("ready")}
        unique_column_sets = {tuple(index.get("columns", [])) for index in indexes if index.get("unique") and index.get("valid") and index.get("ready")}
        expected_index_names = REQUIRED_INDEXES.get(key, set())
        expected_unique_sets = REQUIRED_UNIQUE_COLUMNS.get(key, set())
        missing_indexes = sorted(expected_index_names - actual_index_names)
        missing_uniques = sorted(expected_unique_sets - unique_column_sets)
        item["indexes"] = sorted(actual_index_names)
        item["constraints"] = [list(columns) for columns in sorted(unique_column_sets)]
        item["index_status"] = "READY" if not missing_indexes else "MISMATCH"
        item["constraint_status"] = "READY" if not missing_uniques else "MISMATCH"
        item["missing_indexes"] = missing_indexes
        item["missing_unique_constraints"] = [list(columns) for columns in missing_uniques]
        actual_fks = {
            (column, fk.get("target_schema"), fk.get("target_table"), target_column)
            for fk in (metadata or {}).get("foreign_keys", []) if fk.get("validated")
            for column, target_column in zip(fk.get("columns", []), fk.get("target_columns", []))
        }
        missing_fks = sorted(REQUIRED_FOREIGN_KEYS.get(key, set()) - actual_fks)
        item["foreign_keys"] = (metadata or {}).get("foreign_keys", [])
        item["foreign_key_status"] = "READY" if not missing_fks else "MISMATCH"
        item["missing_foreign_keys"] = [list(fk) for fk in missing_fks]
        access = (metadata or {}).get("access", {})
        if key in RESTRICTED_TABLES:
            denied_public = all(not access.get(f"{role}_{operation}", True)
                                for role in ("anon", "authenticated")
                                for operation in ("select", "insert", "update", "delete"))
            if key in {("public", "tax_rules"), ("public", "energy_prices")}:
                service_role_access = (access.get("service_role_select", False)
                                       and all(not access.get(f"service_role_{operation}", True)
                                               for operation in ("insert", "update", "delete")))
            else:
                service_role_access = all(access.get(f"service_role_{operation}", False)
                                          for operation in ("select", "insert", "update", "delete"))
            security_ready = bool((metadata or {}).get("rls_enabled")) and denied_public and service_role_access
        else:
            security_ready = True
        item["rls_enabled"] = (metadata or {}).get("rls_enabled")
        item["access"] = access
        item["security_status"] = "READY" if security_ready else "MISMATCH"
        if item["status"] == "READY" and (missing_indexes or missing_uniques or missing_fks or not security_ready):
            item["status"] = "MISMATCH"
    repo = _repository_table_references()
    campaign_rpc = "/rpc/consume_campaign_handoff" in (openapis.get("public") or {}).get("paths", {})
    contract_rpc = "/rpc/dev_schema_contract" in (openapis.get("public") or {}).get("paths", {}) and metadata_rpc is not None
    consume_fn = next((function for function in (metadata_rpc or {}).get("functions", []) if function.get("name") == "consume_campaign_handoff"), None)
    campaign_rpc = campaign_rpc and bool(consume_fn and consume_fn.get("args", "").strip() == "p_token_hash text")
    campaign_rpc = campaign_rpc and bool(consume_fn and consume_fn.get("service_role_execute") and not consume_fn.get("anon_execute") and not consume_fn.get("authenticated_execute"))
    blockers = [item for item in result if item["status"] != "READY"]
    if not contract_rpc or not campaign_rpc:
        blockers.append({"schema": "public", "table": "RPC contract", "status": "MISMATCH", "missing_columns": [], "unexpected_columns": []})
    return {
        "status": "READY" if not blockers else "BLOCKED",
        "project_host": url.split("/")[2] if "/" in url else "configured",
        "app_env": settings.app_env,
        "tables": result,
        "repository_table_routing": repo,
        "campaign_rpc_in_openapi": campaign_rpc,
        "catalog_metadata_rpc": contract_rpc,
        "catalog_metadata_error": metadata_error,
        "schemas": (metadata_rpc or {}).get("schemas", []),
        "catalog_limitations": "Catalog metadata is read through service-role-only public.dev_schema_contract(); this verifies columns, index definitions, unique-index column sets, and RPC arguments.",
    }


if __name__ == "__main__":
    report = audit()
    if "--summary" in sys.argv:
        compact = {
            "status": report.get("status"),
            "error": report.get("error"),
            "project_host": report.get("project_host"),
            "app_env": report.get("app_env"),
            "counts": {},
            "tables": [
                {key: item.get(key) for key in ("schema", "table", "status", "missing_columns", "unexpected_columns", "index_status", "constraint_status", "foreign_key_status", "security_status", "missing_indexes", "missing_unique_constraints", "missing_foreign_keys", "http_status", "postgrest_code")}
                for item in report.get("tables", [])
            ],
            "campaign_rpc_in_openapi": report.get("campaign_rpc_in_openapi"),
            "catalog_metadata_rpc": report.get("catalog_metadata_rpc"),
            "catalog_metadata_error": report.get("catalog_metadata_error"),
            "catalog_limitations": report.get("catalog_limitations"),
        }
        for table in report.get("tables", []):
            compact["counts"][table["status"]] = compact["counts"].get(table["status"], 0) + 1
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["status"] == "READY" else 1)
