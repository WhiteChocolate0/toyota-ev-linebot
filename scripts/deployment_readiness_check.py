#!/usr/bin/env python3
"""Fail-closed pre-deployment check. All database checks are read-only."""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings  # noqa: E402
from app.services.environment_safety import EnvironmentSafetyError, validate_database_environment  # noqa: E402
from scripts.check_db_schema import audit  # noqa: E402


def main() -> int:
    settings = get_settings()
    required_env = {
        "SUPABASE_URL": bool(settings.supabase_url),
        "SUPABASE_SERVICE_ROLE_KEY": bool(settings.supabase_service_role_key),
        "LINE_CHANNEL_SECRET": bool(settings.line_channel_secret),
        "LINE_CHANNEL_ACCESS_TOKEN": bool(settings.line_channel_access_token),
    }
    project_ref = settings.supabase_project_ref or (settings.supabase_url.split("//", 1)[-1].split(".", 1)[0] if settings.supabase_url else "")
    try:
        validate_database_environment(settings, operation="deployment readiness check")
        env_consistent, environment_error = True, None
    except EnvironmentSafetyError as exc:
        env_consistent, environment_error = False, str(exc)
    imports: dict[str, str] = {}
    for module in ("app.main", "app.services.linebot_repository", "app.services.shared_reference_repository", "app.services.event_processor"):
        try:
            importlib.import_module(module)
            imports[module] = "OK"
        except Exception as exc:  # noqa: BLE001
            imports[module] = f"FAIL: {type(exc).__name__}"
    schema = audit()
    checks = {
        "required_env": "READY" if all(required_env.values()) else "BLOCKED",
        "environment_project_match": "READY" if env_consistent else "BLOCKED",
        "repository_imports": "READY" if all(value == "OK" for value in imports.values()) else "BLOCKED",
        "db_schema": schema.get("status", "BLOCKED"),
        "shared_vehicle_table": "READY" if any(t["schema"] == "public" and t["table"] == "vehicle_profiles" and t["status"] == "READY" for t in schema.get("tables", [])) else "BLOCKED",
        "knowledge_table": "READY" if any(t["schema"] == "public" and t["table"] == "knowledge_sources" and t["status"] == "READY" for t in schema.get("tables", [])) else "BLOCKED",
        "campaign_token_table": "READY" if any(t["schema"] == "campaign" and t["table"] == "link_tokens" and t["status"] == "READY" for t in schema.get("tables", [])) else "BLOCKED",
    }
    result = {
        "status": "READY_TO_DEPLOY" if all(value == "READY" for value in checks.values()) else "BLOCKED",
        "checks": checks,
        "environment": {"app_env": settings.app_env, "project_ref": project_ref, "required_env_present": required_env},
        "imports": imports,
        "schema_audit": {
            "status": schema.get("status"),
            "counts": {status: sum(1 for item in schema.get("tables", []) if item["status"] == status) for status in sorted({item["status"] for item in schema.get("tables", [])})},
            "tables": [{key: item.get(key) for key in ("schema", "table", "actual_schema", "status", "missing_columns", "unexpected_columns")} for item in schema.get("tables", [])],
            "campaign_rpc_in_openapi": schema.get("campaign_rpc_in_openapi"),
        },
        "write_policy": "No Production writes or test fixtures performed.",
    }
    blockers = []
    for component, value in checks.items():
        if value != "READY":
            reason = environment_error if component == "environment_project_match" else f"{component} check returned {value}."
            blockers.append({"severity": "P0" if component in {"environment_project_match", "db_schema"} else "P1", "component": component, "reason": reason, "required_action": "Correct the configuration or schema, then rerun this read-only check."})
    result["blockers"] = blockers
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "READY_TO_DEPLOY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
