#!/usr/bin/env python3
"""Run guarded, low-volume integration checks against the MVP/DEV database.

Campaign fixtures are synthetic and are removed in a finally block. This
script never inserts or reads raw organizer CDP rows.
"""
from __future__ import annotations

import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.services.environment_safety import EnvironmentSafetyError, require_nonproduction_database_write


def main() -> int:
    settings = get_settings()
    try:
        env = require_nonproduction_database_write(settings, operation="DEV data smoke tests")
    except EnvironmentSafetyError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    if env.project_ref != "extkwpghjfttamontqkl":
        print(f"BLOCKED: unexpected MVP/DEV project ref {env.project_ref!r}", file=sys.stderr)
        return 1
    from supabase import create_client
    from app.services.internal_insights_service import InternalInsightsService
    from app.services.linebot_repository import LinebotRepository
    from app.services.shared_reference_repository import SharedReferenceRepository

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    public = client.schema("public")
    campaign = client.schema("campaign")
    source_ids = ["organizer_toyota_brand_survey_2025_w3", "organizer_cdp_t_vehicles_2026"]
    results: dict[str, object] = {}

    # Import completeness and data-quality gates.
    sources = public.table("internal_research_sources").select("id,visibility,source_kind").in_("id", source_ids).execute().data or []
    concerns = public.table("internal_concern_priorities").select("id,visibility,research_source_id").eq("research_source_id", source_ids[0]).execute().data or []
    mappings = public.table("internal_vehicle_alias_mappings").select("vehicle_id,mapping_status,source_id").eq("source_id", source_ids[1]).execute().data or []
    benchmarks = public.table("internal_vehicle_service_benchmarks").select("vehicle_id,vehicle_age_bucket,sample_size,currency_type,source_id,visibility,status,avg_service_visits").eq("source_id", source_ids[1]).execute().data or []
    mapped_ids = {row["vehicle_id"] for row in mappings if row.get("mapping_status") == "MAPPED" and row.get("vehicle_id")}
    valid_buckets = {"0-12", "13-24", "25-36", "37-59", "60+"}
    assert len(sources) == 2 and all(row["visibility"] == "INTERNAL_ORGANIZER" for row in sources)
    assert len(concerns) == 11 and all(row["visibility"] == "INTERNAL_ORGANIZER" for row in concerns)
    assert len(mappings) == 27
    assert len(benchmarks) == 25 and all(row["vehicle_id"] in mapped_ids for row in benchmarks)
    assert all(row["vehicle_age_bucket"] in valid_buckets and int(row["sample_size"]) >= 30 for row in benchmarks)
    assert all(row["currency_type"] == "ANONYMIZED_A_CURRENCY" and row["visibility"] == "INTERNAL_ORGANIZER" for row in benchmarks)
    assert all(row["status"] == "READY" for row in benchmarks)
    assert sum(1 for row in mappings if row["mapping_status"] in {"UNMAPPED", "UNMAPPED_AMBIGUOUS"}) == 22
    results["import"] = {"sources": len(sources), "concerns": len(concerns), "mappings": len(mappings), "benchmarks": len(benchmarks), "unmapped_or_ambiguous": 22, "quality_gates": "PASS"}

    # Backend-only internal reads and sample-size gate.
    repository = LinebotRepository()
    insights = InternalInsightsService(repository)
    top = insights.get_top_bev_concerns()
    assert len(top) == 11 and all(item.get("visibility") == "INTERNAL_ORGANIZER" for item in top)
    first = benchmarks[0]
    item = insights.get_vehicle_service_benchmark(first["vehicle_id"], first["vehicle_age_bucket"])
    assert item.get("status") == "READY" and item.get("currency_type") == "ANONYMIZED_A_CURRENCY"
    comparison = insights.compare_service_frequency(first["vehicle_id"], first["vehicle_id"], first["vehicle_age_bucket"])
    assert comparison.get("status") == "READY"
    results["insights"] = {"top_concerns": "PASS", "benchmark": "PASS", "same-cohort comparison": "PASS"}

    # Public retrieval stays official-only; reference tables remain readable.
    shared = SharedReferenceRepository(client)
    public_sources = shared.search_knowledge_sources(query="電動車", topic=None, terms=("電動車",))
    assert all(str(row.get("source_type", "")).casefold() in {"official", "public_official", "government", "manufacturer", "owner_manual", "toyota_official"} for row in public_sources)
    tax_rows = shared.get_tax_rules()
    energy_rows = shared.get_energy_prices()
    results["reference"] = {"tax_rules_read": "PASS", "tax_rows": len(tax_rows), "energy_prices_read": "PASS", "energy_rows": len(energy_rows), "public_rag_official_only": "PASS"}

    # Prefer a direct anon-key denial test; if no anon key is configured,
    # verify the actual PostgreSQL grants through the service-only catalog RPC.
    if settings.supabase_anon_key:
        anon = create_client(settings.supabase_url, settings.supabase_anon_key)
        anon_write_denied = False
        try:
            anon.schema("public").table("internal_research_sources").insert({
                "id": f"smoke-{uuid.uuid4()}", "title": "synthetic access test",
                "source_kind": "INTERNAL_ORGANIZER_RESEARCH", "snapshot_period": "smoke",
                "visibility": "INTERNAL_ORGANIZER",
            }).execute()
        except Exception:
            anon_write_denied = True
        assert anon_write_denied
        boundary_method = "anon key write denied"
    else:
        contract = client.rpc("dev_schema_contract", {}).execute().data
        if isinstance(contract, list):
            contract = contract[0]
        internal = [row for row in contract.get("tables", []) if row.get("schema") == "public" and row.get("table", "").startswith("internal_")]
        assert len(internal) == 4
        assert all(row.get("rls_enabled") and all(not row.get("access", {}).get(f"{role}_{op}", True) for role in ("anon", "authenticated") for op in ("select", "insert", "update", "delete")) for row in internal)
        assert all(row.get("access", {}).get("service_role_select") and row.get("access", {}).get("service_role_insert") for row in internal)
        boundary_method = "database RLS/grant catalog verified (anon key not configured)"
    results["internal_boundary"] = {"status": "PASS", "method": boundary_method}

    # Isolated campaign fixtures; all test IDs are random and cleaned up.
    session_id, result_id = str(uuid.uuid4()), str(uuid.uuid4())
    tokens: list[str] = []
    now = datetime.now(UTC)
    session_row = {"id": session_id, "anonymous_session_id": str(uuid.uuid4()), "started_at": now.isoformat(), "completed_at": now.isoformat(), "status": "completed", "created_at": now.isoformat(), "updated_at": now.isoformat()}
    result_row = {"id": result_id, "quiz_session_id": session_id, "defense_value": 50, "persona_key": "SMOKE_TEST", "ability_scores_json": {"synthetic": 1}, "result_summary": "Synthetic DEV smoke fixture", "created_at": now.isoformat()}
    try:
        campaign.table("quiz_sessions").insert(session_row).execute()
        campaign.table("quiz_results").insert(result_row).execute()
        valid_hash, expired_hash = secrets.token_hex(32), secrets.token_hex(32)
        tokens = [valid_hash, expired_hash]
        campaign.table("link_tokens").insert([
            {"id": str(uuid.uuid4()), "quiz_result_id": result_id, "token_hash": valid_hash, "status": "active", "expires_at": (now + timedelta(minutes=5)).isoformat()},
            {"id": str(uuid.uuid4()), "quiz_result_id": result_id, "token_hash": expired_hash, "status": "active", "expires_at": (now - timedelta(minutes=5)).isoformat()},
        ]).execute()
        valid = client.rpc("consume_campaign_handoff", {"p_token_hash": valid_hash}).execute().data
        second = client.rpc("consume_campaign_handoff", {"p_token_hash": valid_hash}).execute().data
        expired = client.rpc("consume_campaign_handoff", {"p_token_hash": expired_hash}).execute().data
        invalid = client.rpc("consume_campaign_handoff", {"p_token_hash": secrets.token_hex(32)}).execute().data
        assert (valid[0] if isinstance(valid, list) else valid).get("status") == "ok"
        assert (second[0] if isinstance(second, list) else second).get("status") == "consumed"
        assert (expired[0] if isinstance(expired, list) else expired).get("status") == "expired"
        assert (invalid[0] if isinstance(invalid, list) else invalid).get("status") == "invalid"
        results["campaign_handoff"] = {"valid": "PASS", "second_consume": "PASS", "expired": "PASS", "invalid": "PASS", "synthetic_only": True}
    finally:
        if tokens:
            campaign.table("link_tokens").delete().in_("token_hash", tokens).execute()
        campaign.table("quiz_results").delete().eq("id", result_id).execute()
        campaign.table("quiz_sessions").delete().eq("id", session_id).execute()

    print({"status": "PASS", "project_ref": env.project_ref, "results": results})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"BLOCKED: smoke assertion failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
