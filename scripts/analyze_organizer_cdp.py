#!/usr/bin/env python3
"""Offline, privacy-minimizing analysis of organizer-provided CDP CSVs.

Raw records and demographic fields stay in memory and are never written to an
output. Only model-level aggregates, mapping statuses, and quality counts are
exported. No TCO or user-facing knowledge data is created.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_INPUT = Path("/Users/anniepai/Documents/NSYSU/和泰黑客松/TOYOTA EV新生活 競賽數據")
MIN_BENCHMARK_SAMPLE_SIZE = 30

FIELDS = {
    "record_id": ("編號", "4.3"),
    "gender": ("性別",),
    "age": ("年齡",),
    "region": ("居住縣市",),
    "service_amount": ("回廠消費總金額",),
    "service_visits": ("近一年回廠次數",),
    "paid_service_visits": ("近一年有費回廠次數",),
    "scheduled_visits": ("近一年回廠有費定保次數", "近一年定保次數"),
    "maintenance_amount": ("近一年定保消費金額",),
    "repair_visits": ("近一年維修次數",),
    "vehicle_model": ("現保有車款",),
    "delivery_date": ("現保有車交車日期",),
}
NUMERIC_FIELDS = ("service_amount", "service_visits", "paid_service_visits", "scheduled_visits", "maintenance_amount", "repair_visits")
COUNT_FIELDS = ("service_visits", "paid_service_visits", "scheduled_visits", "repair_visits")
DEMOGRAPHIC_FIELDS = {"gender", "age", "region"}
MISSING_VALUES = {"", "na", "n/a", "null", "none", "-", "--", "未提供", "不詳", "無資料"}
AGE_BUCKETS = ((0, 12, "0-12"), (13, 24, "13-24"), (25, 36, "25-36"), (37, 59, "37-59"), (60, 10_000, "60+"))

# The normalized name must uniquely identify one current shared vehicle profile.
# Ambiguous family-level names intentionally remain UNMAPPED.
EXPLICIT_ALIAS_HINTS: dict[str, str] = {
    "ALTISHV": "ALTIS HYBRID豪華",
}


def normalize_column_name(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).replace("\r", " ").replace("\n", " ")).strip()


def normalize_model(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().upper()
    text = re.sub(r"[\s\-_()（）]+", "", text)
    text = text.replace("COROLLACROSS", "CCROSS")
    text = text.replace("HYBRID", "HV").replace("油電", "HV")
    text = text.replace("BZ4X", "BZ4X")
    return text


def resolve_fields(headers: list[str]) -> dict[str, int | None]:
    normalized = [normalize_column_name(h) for h in headers]
    resolved: dict[str, int | None] = {}
    for field, variants in FIELDS.items():
        wanted = [normalize_column_name(v) for v in variants]
        index = next((i for i, name in enumerate(normalized) if any(v in name for v in wanted)), None)
        resolved[field] = index
    return resolved


def parse_number(value: str) -> tuple[float | None, str | None]:
    text = unicodedata.normalize("NFKC", value or "").strip().replace(",", "").replace("，", "")
    if text.casefold() in MISSING_VALUES:
        return None, None
    text = text.replace("元", "").replace("$", "").replace("＄", "")
    try:
        number = float(text)
    except ValueError:
        return None, "not_numeric"
    if not math.isfinite(number):
        return None, "not_finite"
    if number < 0:
        return None, "negative"
    return number, None


def parse_delivery_date(value: str) -> date | None:
    text = unicodedata.normalize("NFKC", value or "").strip()
    if text.casefold() in MISSING_VALUES:
        return None
    text = text.replace("年", "/").replace("月", "/").replace("日", "")
    text = re.sub(r"[.\-]", "/", text)
    match = re.search(r"(?<!\d)(\d{2,4})/(\d{1,2})/(\d{1,2})(?!\d)", text)
    if match:
        year, month, day = map(int, match.groups())
        if year < 1911:
            year += 1911
        try:
            return date(year, month, day)
        except ValueError:
            return None
    compact = re.search(r"(?<!\d)(\d{3})(\d{2})(\d{2})(?!\d)", text)
    if compact:
        year, month, day = map(int, compact.groups())
        try:
            return date(year + 1911, month, day)
        except ValueError:
            return None
    compact_gregorian = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", text)
    if compact_gregorian:
        year, month, day = map(int, compact_gregorian.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def age_months(delivery: date, snapshot: date) -> int | None:
    months = (snapshot.year - delivery.year) * 12 + snapshot.month - delivery.month
    if snapshot.day < delivery.day:
        months -= 1
    return months if months >= 0 else None


def age_bucket(months: int | None) -> str | None:
    if months is None:
        return None
    for lower, upper, label in AGE_BUCKETS:
        if lower <= months <= upper:
            return label
    return None


def load_catalog(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    if path.suffix.casefold() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else rows.get("data", [])
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def map_model(raw: str, catalog: list[dict[str, Any]]) -> tuple[str | None, str]:
    norm = normalize_model(raw)
    if not norm or not catalog:
        return None, "UNMAPPED"
    hinted = EXPLICIT_ALIAS_HINTS.get(norm)
    candidates = []
    for profile in catalog:
        model_name = normalize_model(str(profile.get("model_name", "")))
        trim = normalize_model(str(profile.get("trim_name", "")))
        aliases = profile.get("aliases", [])
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except json.JSONDecodeError:
                aliases = [aliases]
        tokens = {model_name, *(normalize_model(str(a)) for a in (aliases or []))}
        drivetrain = normalize_model(str(profile.get("drivetrain", "")))
        raw_hybrid_marker = norm.endswith("HV") or norm.endswith("HYBRID")
        profile_is_hybrid = drivetrain in {"HEV", "HYBRID", "HV", "油電"} or "HYBRID" in model_name or "HV" in model_name
        if profile_is_hybrid and not raw_hybrid_marker and not hinted:
            continue
        if raw_hybrid_marker and drivetrain and drivetrain not in {"HEV", "HYBRID", "HV", "油電"} and not hinted:
            continue
        if hinted:
            if normalize_model(str(profile.get("model_name", "")) + str(profile.get("trim_name", ""))) == normalize_model(hinted):
                candidates.append(profile)
            continue
        if norm in tokens or (trim and norm == model_name + trim):
            candidates.append(profile)
    unique = {str(row.get("id")): row for row in candidates if row.get("id")}
    if len(unique) == 1:
        return next(iter(unique)), "MAPPED"
    return None, "UNMAPPED" if not unique else "UNMAPPED_AMBIGUOUS"


def candidate_canonical_vehicles(raw: str, catalog: list[dict[str, Any]]) -> list[str]:
    """Return matching active candidates for review; never choose among them."""
    norm = normalize_model(raw)
    hinted = EXPLICIT_ALIAS_HINTS.get(norm)
    labels: dict[str, str] = {}
    for profile in catalog:
        model_name = normalize_model(str(profile.get("model_name", "")))
        trim = normalize_model(str(profile.get("trim_name", "")))
        aliases = profile.get("aliases", [])
        if isinstance(aliases, str):
            try: aliases = json.loads(aliases)
            except json.JSONDecodeError: aliases = [aliases]
        tokens = {model_name, *(normalize_model(str(alias)) for alias in (aliases or []))}
        drivetrain = normalize_model(str(profile.get("drivetrain", "")))
        hybrid = norm.endswith("HV")
        profile_hybrid = drivetrain in {"HEV", "HYBRID", "HV", "油電"} or "HYBRID" in model_name or "HV" in model_name
        matches = (hinted and normalize_model(str(profile.get("model_name", "")) + str(profile.get("trim_name", ""))) == normalize_model(hinted)) or (not hinted and (norm in tokens or (trim and norm == model_name + trim)))
        if matches and not (profile_hybrid and not hybrid and not hinted) and not (hybrid and drivetrain and drivetrain not in {"HEV", "HYBRID", "HV", "油電"} and not hinted):
            vehicle_id = str(profile.get("id", ""))
            if vehicle_id:
                labels[vehicle_id] = f"{profile.get('model_name', '')} {profile.get('trim_name', '')}".strip() + f" ({vehicle_id})"
    return [labels[key] for key in sorted(labels)]


def quantile_outliers(values: list[float]) -> dict[str, Any]:
    if len(values) < 4:
        return {"count": 0, "lower_bound": None, "upper_bound": None}
    ordered = sorted(values)
    q1, q3 = statistics.quantiles(ordered, n=4, method="inclusive")[0], statistics.quantiles(ordered, n=4, method="inclusive")[2]
    spread = q3 - q1
    lower, upper = q1 - 1.5 * spread, q3 + 1.5 * spread
    return {"count": sum(v < lower or v > upper for v in values), "lower_bound": round(lower, 3), "upper_bound": round(upper, 3)}


def csv_sources(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("*.csv"))


def analyze(input_dir: Path, output_dir: Path, snapshot: date, catalog_path: Path | None) -> dict[str, Any]:
    sources = csv_sources(input_dir)
    if not sources:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")
    if catalog_path is not None and str(catalog_path) == "CONFIGURED_SHARED_CATALOG":
        from app.config import get_settings
        from app.services.environment_safety import validate_database_environment
        from supabase import create_client
        settings = get_settings()
        validate_database_environment(settings, operation="shared catalog analysis")
        if settings.supabase_url and settings.supabase_service_role_key:
            response = create_client(settings.supabase_url, settings.supabase_service_role_key).schema("public").table("vehicle_profiles").select("id,model_name,trim_name,aliases,drivetrain").eq("is_active", True).execute()
            catalog = response.data or []
        else:
            catalog = []
    else:
        catalog = load_catalog(catalog_path)
    total_rows = 0
    exact_duplicates = 0
    field_missing: Counter[str] = Counter()
    invalid_numeric: Counter[str] = Counter()
    missing_field_counts: Counter[str] = Counter()
    invalid_delivery_dates = 0
    future_delivery_dates = 0
    numeric_values: dict[str, list[float]] = defaultdict(list)
    models: Counter[str] = Counter()
    model_status: dict[str, tuple[str | None, str]] = {}
    cohort_counts: Counter[tuple[str, str]] = Counter()
    buckets: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    seen_hashes: set[str] = set()
    file_reports: list[dict[str, Any]] = []

    for path in sources:
        rows_in_file = 0
        selected_encoding = None
        for encoding in ("utf-8-sig", "cp950", "big5"):
            try:
                stream = path.open("r", encoding=encoding, newline="")
                reader = csv.reader(stream)
                headers = next(reader, [])
                selected_encoding = encoding
                break
            except UnicodeDecodeError:
                try:
                    stream.close()
                except UnboundLocalError:
                    pass
        if not selected_encoding:
            raise UnicodeError(f"Could not decode {path.name} as UTF-8, CP950, or Big5")
        indices = resolve_fields(headers)
        for field, index in indices.items():
            if index is None:
                missing_field_counts[field] += 1
        try:
            for row in reader:
                if not row or not any(cell.strip() for cell in row):
                    continue
                total_rows += 1
                rows_in_file += 1
                padded = row + [""] * max(0, len(headers) - len(row))
                # Hash the normalized source row transiently for exact duplicate detection.
                fingerprint_values = [normalize_column_name(cell).casefold() for i, cell in enumerate(padded[:len(headers)]) if i != indices["record_id"]]
                fingerprint = hashlib.sha256("\x1f".join(fingerprint_values).encode("utf-8")).hexdigest()
                if fingerprint in seen_hashes:
                    exact_duplicates += 1
                    continue
                seen_hashes.add(fingerprint)

                raw_model = padded[indices["vehicle_model"]].strip() if indices["vehicle_model"] is not None else ""
                normalized_model = normalize_model(raw_model)
                if not normalized_model or normalized_model.casefold() in MISSING_VALUES:
                    field_missing["vehicle_model"] += 1
                    continue
                models[raw_model.strip()] += 1
                if raw_model not in model_status:
                    model_status[raw_model] = map_model(raw_model, catalog)
                vehicle_id, _mapping_status = model_status[raw_model]

                delivery_text = padded[indices["delivery_date"]].strip() if indices["delivery_date"] is not None else ""
                delivery = parse_delivery_date(delivery_text)
                if not delivery_text or delivery_text.casefold() in MISSING_VALUES:
                    field_missing["delivery_date"] += 1
                if delivery_text.casefold() not in MISSING_VALUES and not delivery:
                    invalid_delivery_dates += 1
                months = age_months(delivery, snapshot) if delivery else None
                if delivery and months is None:
                    future_delivery_dates += 1
                bucket = age_bucket(months)
                if bucket and vehicle_id:
                    cohort_counts[(str(vehicle_id), bucket)] += 1

                parsed: dict[str, float | None] = {}
                for field in NUMERIC_FIELDS:
                    index = indices[field]
                    raw = padded[index].strip() if index is not None else ""
                    if not raw or raw.casefold() in MISSING_VALUES:
                        field_missing[field] += 1
                        parsed[field] = None
                        continue
                    number, reason = parse_number(raw)
                    if reason:
                        invalid_numeric[field] += 1
                    elif field in COUNT_FIELDS and number is not None and not number.is_integer():
                        invalid_numeric[field] += 1
                        number = None
                    parsed[field] = number
                    if number is not None:
                        numeric_values[field].append(number)
                if bucket and vehicle_id:
                    key = (str(vehicle_id), bucket)
                    for field, number in parsed.items():
                        if number is not None:
                            buckets[key][field].append(number)
        finally:
            stream.close()
        file_reports.append({"file": path.name, "encoding": selected_encoding, "columns": len(headers), "rows": rows_in_file, "unresolved_fields": [field for field, idx in indices.items() if idx is None]})

    def mean_median(key: tuple[str, str], field: str) -> tuple[float | None, float | None]:
        values = buckets[key].get(field, [])
        if not values:
            return None, None
        return round(statistics.fmean(values), 3), round(statistics.median(values), 3)

    metrics = (
        ("service_visits", "avg_service_visits", "median_service_visits"),
        ("paid_service_visits", "avg_paid_service_visits", "median_paid_service_visits"),
        ("scheduled_visits", "avg_scheduled_maintenance_visits", "median_scheduled_maintenance_visits"),
        ("repair_visits", "avg_repair_visits", "median_repair_visits"),
        ("service_amount", "avg_service_amount_a_currency", "median_service_amount_a_currency"),
        ("maintenance_amount", "avg_maintenance_amount_a_currency", "median_maintenance_amount_a_currency"),
    )
    benchmark_rows: list[dict[str, Any]] = []
    for (vehicle_id, bucket), sample_size in sorted(cohort_counts.items()):
        record: dict[str, Any] = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"organizer-cdp:{vehicle_id}:{bucket}:{snapshot.isoformat()}")),
            "vehicle_id": vehicle_id,
            "vehicle_age_bucket": bucket,
            "sample_size": sample_size,
            "currency_type": "ANONYMIZED_A_CURRENCY",
            "source_id": "organizer_cdp_t_vehicles_2026",
            "snapshot_date": snapshot.isoformat(),
            "visibility": "INTERNAL_ORGANIZER",
            "status": "READY" if sample_size >= MIN_BENCHMARK_SAMPLE_SIZE else "INSUFFICIENT_SAMPLE",
        }
        for field, avg_col, median_col in metrics:
            avg, median = mean_median((vehicle_id, bucket), field)
            record[avg_col] = avg if sample_size >= MIN_BENCHMARK_SAMPLE_SIZE else None
            record[median_col] = median if sample_size >= MIN_BENCHMARK_SAMPLE_SIZE else None
        benchmark_rows.append(record)

    mapping_rows = []
    for raw, count in sorted(models.items(), key=lambda item: item[0].casefold()):
        vehicle_id, status = model_status.get(raw, (None, "UNMAPPED"))
        mapping_rows.append({"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"organizer-alias:{raw.casefold()}")), "raw_model_name": raw, "normalized_model_name": normalize_model(raw), "vehicle_id": vehicle_id or "", "mapping_status": status, "candidate_canonical_vehicles": " | ".join(candidate_canonical_vehicles(raw, catalog)), "source_id": "organizer_cdp_t_vehicles_2026", "snapshot_date": snapshot.isoformat(), "sample_size": count, "visibility": "INTERNAL_ORGANIZER"})

    denominator = total_rows - exact_duplicates
    quality = {
        "total_rows": total_rows,
        "distinct_rows_after_exact_dedup": denominator,
        "exact_duplicate_rows": exact_duplicates,
        "source_files": file_reports,
        "vehicle_distribution": [{"raw_model_name": model, "count": count} for model, count in models.most_common()],
        "missing_rate": {field: {"count": field_missing[field], "rate": round(field_missing[field] / max(denominator, 1), 6)} for field in (*NUMERIC_FIELDS, "vehicle_model", "delivery_date")},
        "required_fields_not_found_in_source": dict(missing_field_counts),
        "invalid_delivery_dates": invalid_delivery_dates,
        "future_delivery_dates": future_delivery_dates,
        "invalid_numeric_values": dict(invalid_numeric),
        "unmapped_vehicles": [{"raw_model_name": row["raw_model_name"], "status": row["mapping_status"], "sample_size": row["sample_size"]} for row in mapping_rows if row["mapping_status"] != "MAPPED"],
        "cohort_sample_sizes": [{"vehicle_id": vehicle_id, "vehicle_age_bucket": bucket, "sample_size": count, "status": "READY" if count >= MIN_BENCHMARK_SAMPLE_SIZE else "INSUFFICIENT_SAMPLE"} for (vehicle_id, bucket), count in sorted(cohort_counts.items())],
        "suspicious_outliers": {field: quantile_outliers(values) for field, values in numeric_values.items()},
        "currency_type": "ANONYMIZED_A_CURRENCY",
        "min_benchmark_sample_size": MIN_BENCHMARK_SAMPLE_SIZE,
        "age_bucket_policy": "0-12, 13-24, 25-36, 37-59, 60+ months; 60+ is used to keep buckets mutually exclusive.",
        "demographic_fields_used_for_aggregation": [],
        "raw_rows_written": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "internal_vehicle_service_benchmarks.csv", benchmark_rows)
    _write_csv(output_dir / "vehicle_alias_mapping.csv", mapping_rows)
    from app.services.internal_concern_priorities import CONCERN_PRIORITY_ROWS, RESEARCH_SOURCE_ID, SNAPSHOT_PERIOD, VISIBILITY
    concern_rows = [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{RESEARCH_SOURCE_ID}:{row['concern_type']}:{SNAPSHOT_PERIOD}")), **row, "weight": round(float(row["weight"]) / 100, 4), "research_source_id": RESEARCH_SOURCE_ID, "snapshot_period": SNAPSHOT_PERIOD, "visibility": VISIBILITY, "created_at": datetime.now().astimezone().isoformat()} for row in CONCERN_PRIORITY_ROWS]
    _write_csv(output_dir / "internal_concern_priorities.csv", concern_rows)
    (output_dir / "data_quality_summary.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_quality_report(ROOT / "docs/organizer_data_quality_report.md", quality)
    _write_unmapped_models_report(ROOT / "docs/unmapped_vehicle_models.md", mapping_rows)
    return quality


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_quality_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# 主辦方補充資料品質報告", "",
        "本報告只列匿名聚合與品質計數。CSV 原始列與 demographic 欄位不會寫入輸出。金額欄位以 `ANONYMIZED_A_CURRENCY` 標記，不視為新台幣。", "",
        "## 資料範圍", "", f"- 總輸入列數：{report['total_rows']:,}", f"- 完全重複列：{report['exact_duplicate_rows']:,}", f"- 去重後列數：{report['distinct_rows_after_exact_dedup']:,}",
    ]
    for item in report["source_files"]:
        lines.append(f"- `{item['file']}`：{item['rows']:,} 列，{item['encoding']}，{item['columns']} 欄")
    lines.extend(["", "## 車款與 cohort", "", "| 原始車款名稱 | 列數 | Mapping 狀態 |", "| --- | ---: | --- |"])
    mapping_by_name = {row["raw_model_name"]: row for row in report.get("unmapped_vehicles", [])}
    # Mapping table has the complete status list; only names and counts are shown, never source rows.
    for row in report["vehicle_distribution"]:
        status = next((m["status"] for m in report.get("unmapped_vehicles", []) if m["raw_model_name"] == row["raw_model_name"]), "MAPPED")
        lines.append(f"| {row['raw_model_name']} | {row['count']:,} | {status} |")
    lines.extend(["", "年齡區間採交車日期至 snapshot date 的完整月數；為避免 60 個月同時落入兩區，區間定為 37–59 與 60+。樣本小於門檻者狀態為 `INSUFFICIENT_SAMPLE`，不輸出 benchmark 統計。", "", "| Vehicle ID | 車齡 cohort | 樣本數 | 狀態 |", "| --- | --- | ---: | --- |"])
    for item in report["cohort_sample_sizes"]:
        lines.append(f"| `{item['vehicle_id']}` | {item['vehicle_age_bucket']} | {item['sample_size']:,} | {item['status']} |")
    lines.extend(["", "## 缺漏與無效值", "", "| 欄位 | 缺漏數 | 缺漏率 |", "| --- | ---: | ---: |"])
    for field, value in report["missing_rate"].items():
        lines.append(f"| {field} | {value['count']:,} | {value['rate']:.2%} |")
    lines.append(f"\n交車日期無法解析：{report['invalid_delivery_dates']:,}；未來交車日期：{report['future_delivery_dates']:,}。")
    lines.extend(["", "### 無效數值", ""])
    if report["invalid_numeric_values"]:
        lines.extend(f"- {field}：{count:,}" for field, count in report["invalid_numeric_values"].items())
    else:
        lines.append("- 未發現無效數值。")
    lines.extend(["", "## 疑似離群值", "", "離群值以各欄位 1.5×IQR 作品質提示，不自動刪除。金額只保留 A 國匿名幣值名稱，不換算、不進 TCO。", ""])
    for field, value in report["suspicious_outliers"].items():
        lines.append(f"- {field}：{value['count']:,} 筆")
    lines.extend(["", "## Mapping 限制", "", "名稱若對應多個目前 active `vehicle_profiles` 車型/trim，標記 `UNMAPPED_AMBIGUOUS`；沒有精確候選則標記 `UNMAPPED`。不以品牌、車系或人口特徵猜測 ID。", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_unmapped_models_report(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = ["# Unmapped CDP Vehicle Models", "", "Only `MAPPED` rows with a unique canonical active `vehicle_profiles.id` can enter aggregate benchmarks. `UNMAPPED` and `UNMAPPED_AMBIGUOUS` rows remain excluded; no candidate is auto-selected.", "", "| Raw model | Rows | Status | Candidate canonical vehicles |", "| --- | ---: | --- | --- |"]
    for row in rows:
        if row["mapping_status"] != "MAPPED":
            candidates = row["candidate_canonical_vehicles"] or "—"
            lines.append(f"| {row['raw_model_name']} | {int(row['sample_size']):,} | {row['mapping_status']} | {candidates} |")
    lines.extend(["", "The source-of-truth mapping output is `artifacts/organizer_data_analysis/vehicle_alias_mapping.csv`. A data owner must provide a reviewed canonical vehicle ID before any excluded model can enter a benchmark."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/organizer_data_analysis")
    parser.add_argument("--snapshot-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--vehicle-catalog", type=Path, help="Read-only JSON/CSV snapshot of public.vehicle_profiles")
    parser.add_argument("--use-configured-shared-catalog", action="store_true", help="Read active shared vehicle profiles via configured Supabase credentials; read only")
    args = parser.parse_args()
    try:
        catalog_path = Path("CONFIGURED_SHARED_CATALOG") if args.use_configured_shared_catalog else args.vehicle_catalog
        result = analyze(args.input_dir, args.output_dir, args.snapshot_date, catalog_path)
    except (OSError, ValueError, UnicodeError, csv.Error, RuntimeError) as exc:
        print(f"CDP analysis failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: result[key] for key in ("total_rows", "distinct_rows_after_exact_dedup", "exact_duplicate_rows", "invalid_delivery_dates", "future_delivery_dates", "invalid_numeric_values", "unmapped_vehicles", "cohort_sample_sizes", "suspicious_outliers")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
