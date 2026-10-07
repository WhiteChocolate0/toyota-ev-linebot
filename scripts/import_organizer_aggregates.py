#!/usr/bin/env python3
"""Guarded DEV-only import of anonymous organizer aggregates."""
from __future__ import annotations
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings
from app.services.environment_safety import EnvironmentSafetyError, require_nonproduction_database_write

def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def nullable_values(row: dict) -> dict:
    return {key: (None if value == "" else value) for key, value in row.items()}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/organizer_data_analysis")
    parser.add_argument("--apply", action="store_true", help="Perform the DEV import after safety validation")
    args = parser.parse_args()
    try:
        environment = require_nonproduction_database_write(operation="organizer aggregate import")
    except EnvironmentSafetyError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    files = {"concerns": args.artifact_dir / "internal_concern_priorities.csv", "mappings": args.artifact_dir / "vehicle_alias_mapping.csv", "benchmarks": args.artifact_dir / "internal_vehicle_service_benchmarks.csv"}
    if any(not path.is_file() for path in files.values()):
        print("BLOCKED: aggregate artifact is missing; run analyze_organizer_cdp.py first.", file=sys.stderr)
        return 1
    payloads = {name: [nullable_values(row) for row in rows(path)] for name, path in files.items()}
    # Candidate labels are for human review only and are not part of the DB
    # alias table contract.
    payloads["mappings"] = [
        {key: row.get(key) for key in ("id", "raw_model_name", "normalized_model_name", "vehicle_id", "mapping_status", "source_id", "snapshot_date", "sample_size", "visibility")}
        for row in payloads["mappings"]
    ]
    summary = {name: len(values) for name, values in payloads.items()}
    if not args.apply:
        print({"status": "DRY_RUN", "environment": environment.app_env, "project_ref": environment.project_ref, "rows": summary})
        return 0
    from supabase import create_client
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key).schema("public")
    client.table("internal_research_sources").upsert([
        {"id": "organizer_toyota_brand_survey_2025_w3", "title": "2025 W3 TOYOTA 品牌調查報告", "source_kind": "INTERNAL_ORGANIZER_RESEARCH", "snapshot_period": "2025_W3", "visibility": "INTERNAL_ORGANIZER"},
        {"id": "organizer_cdp_t_vehicles_2026", "title": "2026 AI 黑客松 CDP T 車輛匿名聚合", "source_kind": "INTERNAL_AGGREGATED_CDP", "snapshot_period": "2026", "visibility": "INTERNAL_ORGANIZER"},
    ], on_conflict="id").execute()
    client.table("internal_concern_priorities").upsert(payloads["concerns"], on_conflict="research_source_id,concern_type,snapshot_period").execute()
    client.table("internal_vehicle_alias_mappings").upsert(payloads["mappings"], on_conflict="source_id,raw_model_name,snapshot_date").execute()
    client.table("internal_vehicle_service_benchmarks").upsert(payloads["benchmarks"], on_conflict="vehicle_id,vehicle_age_bucket,source_id,snapshot_date").execute()
    print({"status": "IMPORTED_DEV", "environment": environment.app_env, "project_ref": environment.project_ref, "rows": summary})
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
