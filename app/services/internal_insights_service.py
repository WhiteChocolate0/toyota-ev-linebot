"""Structured-only access to internal organizer aggregates.

This service intentionally has no message rendering and never reads raw CDP rows.
"""
from __future__ import annotations

from app.services.internal_concern_priorities import CONCERN_PRIORITY_ROWS, VISIBILITY

MIN_BENCHMARK_SAMPLE_SIZE = 30


class InternalInsightsService:
    def __init__(self, repository: object | None = None) -> None:
        self.repository = repository

    def get_top_bev_concerns(self, limit: int = 11) -> list[dict]:
        getter = getattr(self.repository, "list_internal_concern_priorities", None)
        if callable(getter):
            rows = getter(limit)
            if rows:
                return rows
        return [
            {**row, "visibility": VISIBILITY, "source_id": "organizer_toyota_brand_survey_2025_w3", "snapshot_period": "2025_W3"}
            for row in CONCERN_PRIORITY_ROWS[:max(0, limit)]
        ]

    def get_vehicle_service_benchmark(self, vehicle_id: str, vehicle_age_bucket: str) -> dict:
        if not vehicle_age_bucket:
            return {"status": "AGE_COHORT_REQUIRED", "vehicle_id": vehicle_id}
        getter = getattr(self.repository, "get_internal_vehicle_service_benchmark", None)
        row = getter(vehicle_id, vehicle_age_bucket) if callable(getter) else None
        if not row:
            return {"status": "NOT_FOUND", "vehicle_id": vehicle_id, "vehicle_age_bucket": vehicle_age_bucket}
        return self._gate(row)

    def compare_service_frequency(self, vehicle_a_id: str, vehicle_b_id: str, vehicle_age_bucket: str) -> dict:
        if not vehicle_age_bucket:
            return {"status": "AGE_COHORT_REQUIRED"}
        a = self.get_vehicle_service_benchmark(vehicle_a_id, vehicle_age_bucket)
        b = self.get_vehicle_service_benchmark(vehicle_b_id, vehicle_age_bucket)
        if a.get("status") != "READY" or b.get("status") != "READY":
            return {"status": "INSUFFICIENT_SAMPLE", "vehicle_age_bucket": vehicle_age_bucket, "vehicles": [a, b]}
        keys = ("avg_service_visits", "median_service_visits", "avg_paid_service_visits", "median_paid_service_visits", "avg_scheduled_maintenance_visits", "median_scheduled_maintenance_visits", "avg_repair_visits", "median_repair_visits")
        return {"status": "READY", "vehicle_age_bucket": vehicle_age_bucket, "vehicles": [{"vehicle_id": x["vehicle_id"], "sample_size": x["sample_size"], **{key: x.get(key) for key in keys}} for x in (a, b)]}

    def get_vehicle_age_distribution(self, vehicle_id: str) -> list[dict]:
        getter = getattr(self.repository, "list_internal_vehicle_age_distribution", None)
        rows = getter(vehicle_id) if callable(getter) else []
        return [{"vehicle_id": vehicle_id, "vehicle_age_bucket": row.get("vehicle_age_bucket"), "sample_size": row.get("sample_size", 0), "status": "READY" if row.get("sample_size", 0) >= MIN_BENCHMARK_SAMPLE_SIZE else "INSUFFICIENT_SAMPLE", "visibility": VISIBILITY} for row in rows]

    @staticmethod
    def _gate(row: dict) -> dict:
        result = {**row, "visibility": VISIBILITY, "currency_type": "ANONYMIZED_A_CURRENCY"}
        if int(row.get("sample_size") or 0) < MIN_BENCHMARK_SAMPLE_SIZE:
            return {"status": "INSUFFICIENT_SAMPLE", "vehicle_id": row.get("vehicle_id"), "vehicle_age_bucket": row.get("vehicle_age_bucket"), "sample_size": row.get("sample_size", 0), "visibility": VISIBILITY}
        result["status"] = "READY"
        return result


internal_insights_service = InternalInsightsService()
