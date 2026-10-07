# DEV Organizer Data Readiness Report

Date: 2026-10-05  
Target: `extkwpghjfttamontqkl` (`APP_ENV=development`, MVP/DEVELOPMENT)

## Overall status: BLOCKED

Aggregate data import and the non-campaign smoke checks passed. Campaign handoff
integration is not fully verified because a synthetic `campaign.quiz_results`
fixture is rejected by the existing `quiz_results_defense_value_check`, and the
repository contains no documented valid `defense_value` range. No schema or
conversation logic was changed to work around that contract.

## Import status

| Check | Result | Evidence |
| --- | --- | --- |
| Environment write safety | PASS | `scripts/check_test_environment.py`: development client allowed for project `extkwpghjfttamontqkl` |
| DEV-only aggregate import | PASS | `scripts/import_organizer_aggregates.py --apply` returned `IMPORTED_DEV` |
| Imported source metadata | PASS | 2 organizer source rows |
| Concern priorities | PASS | 11 rows |
| Vehicle alias mappings | PASS | 27 rows: 5 `MAPPED`, 19 `UNMAPPED`, 3 `UNMAPPED_AMBIGUOUS` |
| Service benchmarks | PASS | 25 rows; five vehicle-age cohorts per uniquely mapped vehicle |
| Raw CDP | NOT IMPORTED | 1,051,612 raw rows remain offline |
| Duplicate handling | PASS | Offline artifact records 1,051,612 raw rows, 3,368 exact duplicates, 1,048,244 deduplicated rows; raw rows were not written |
| Mapping gate | PASS | Analyzer labels a model `MAPPED` only when it has one unique canonical vehicle match; only these IDs occur in the benchmark artifact |
| Currency/sample/cohort gates | PASS | All benchmark rows use `ANONYMIZED_A_CURRENCY`, visibility `INTERNAL_ORGANIZER`, valid cohort buckets, and sample size ≥ 30 (minimum artifact cohort: 902) |

The importer is idempotent upsert-based for these artifacts. No Production project,
Bot state table, campaign token contract, or deployment was touched.

## Schema and application checks

| Component | Result | Notes |
| --- | --- | --- |
| Database schema readiness | PASS | Rechecked after import: `scripts/check_db_schema.py --summary`: 21/21 required tables/RPC contracts READY; internal tables report RLS/grants READY |
| Backend internal reads | PASS | DEV smoke runner read the imported concern and benchmark data via `LinebotRepository` |
| Insights service | PASS | `get_top_bev_concerns()`, `get_vehicle_service_benchmark()`, and `compare_service_frequency()` returned structured aggregate data |
| Sample-size gate | PASS (local test) | Existing boundary test confirms sample size 29 returns `INSUFFICIENT_SAMPLE`; imported DEV cohort rows all exceed the threshold |
| Internal/public boundary | PASS with limitation | `dev_schema_contract()` confirmed RLS enabled, anon/authenticated CRUD denied, and service-role access granted on all four internal tables. No anon key was configured, so no direct anon-key HTTP write attempt was made |
| Public RAG | PASS | Live shared repository search returned only source types in its official allowlist; unit tests reject organizer research/raw CDP sources |
| Demographic minimization / A-currency rendering | PASS (local tests) | Existing tests confirm recommendation ignores demographic fields and A-currency is not rendered as NT$ |
| Reference tables | PASS | DEV repository read of `tax_rules` and `energy_prices` completed; no fixtures were inserted |
| Local regression tests | PASS | `tests/test_campaign_handoff_repository.py` + `tests/test_organizer_data_boundaries.py`: 14 passed |

## Campaign handoff integration

Status: BLOCKED / INCOMPLETE.

The DEV smoke runner verified the environment and completed import, internal
read, RAG, reference-table, and database permission checks. It then attempted to
create a synthetic campaign session and result. Session creation succeeded, but
the result insert was rejected by the pre-existing `campaign.quiz_results`
constraint `quiz_results_defense_value_check`. Attempts with synthetic values
`0` and `50` both failed. The runner's `finally` block deletes its random
session/result/token fixture IDs; the rejected result/token rows were never
created. It did not reach valid, repeated, expired, or invalid token RPC cases.

Required next step: confirm the valid `defense_value` range/type from the
campaign site's authoritative model or migration, then rerun
`scripts/run_dev_data_smoke_tests.py`. Do not weaken or alter the constraint just
to make the smoke test pass.

## Files / execution record

- Importer: `scripts/import_organizer_aggregates.py`
- DEV integration runner: `scripts/run_dev_data_smoke_tests.py`
- Schema verification: `scripts/check_db_schema.py --summary`
- Local organizer boundary regression: 13 passed
- No deploy, raw CDP import, Production write, or Bot state schema change

## Remaining blockers

1. Confirm the campaign `defense_value` fixture contract so handoff RPC cases can
   run using a synthetic result.
2. Configure a DEV anon key if a direct anon-client write-denial smoke test is
   required; current DB privilege/RLS metadata verifies the grant boundary.

Final status: **BLOCKED** (campaign handoff integration not yet verified).
