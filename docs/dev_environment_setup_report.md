# MVP / Development Environment and Schema Check

Date: 2026-10-05

## Environment status: MVP_ENV_READY

| Field | Value | Result |
| --- | --- | --- |
| `APP_ENV` | `development` | PASS |
| `DATABASE_ROLE` | `development` | PASS |
| Current Project Ref | `extkwpghjfttamontqkl` | Designated MVP / DEVELOPMENT DB |
| Production Project Ref | unset | Correct: no real Production project is provisioned |
| Supabase URL Host | `extkwpghjfttamontqkl.supabase.co` | Matches current ref |
| Is Production | `false` | Role-based classification; this project is MVP / DEVELOPMENT |
| Safety Validation | PASS | `validate_database_environment()` passed |
| DB Client Allowed | `true` | Guarded client initialized successfully |
| `scripts/check_test_environment.py` | PASS | DEV/MVP client initialization passed |
| Environment safety tests | PASS | 7 passed, including role mismatch cases |

No credentials or keys are recorded in this report.

## Read-only schema check

`scripts/check_db_schema.py --summary` connected to the configured MVP database after the sandbox network restriction was approved. It performed PostgREST schema inspection only; it did not run migrations or write rows.

Result: **BLOCKED for schema readiness** — 15 expected tables READY, 7 MISSING; `consume_campaign_handoff` was not present in the public PostgREST OpenAPI. Tables reported READY had all required columns; some included additional columns, which are recorded as unexpected by the checker and were not modified. Index/unique metadata could not be fully confirmed because the catalog metadata RPC `dev_schema_contract()` is not available yet.

Missing tables:

- `public.campaign_handoffs`
- `public.internal_concern_priorities`
- `public.internal_research_sources`
- `public.internal_vehicle_alias_mappings`
- `public.internal_vehicle_service_benchmarks`
- `public.tax_rules`
- `public.energy_prices`

Ready campaign tables include `campaign.link_tokens`, `quiz_sessions`, `quiz_answers`, `quiz_results`, and `share_results`. Existing public Bot state tables and shared `vehicle_profiles` / `knowledge_sources` were readable. The `quiz_results` table has an extra `defense_value` column; this is informational and not a blocker for the current environment setup.

## Scope and safety

- `extkwpghjfttamontqkl` is classified as **MVP / DEVELOPMENT**, not Production.
- `PRODUCTION_SUPABASE_PROJECT_REF` remains unset until an actual Production project is created.
- Role guards remain enabled: production app + development DB role and development app + production DB role fail closed; production role also requires an explicit future Production ref.
- No migration, aggregate import, fixture write, smoke-test write, conversation change, or deploy was performed.
- Raw organizer CDP remains offline; no A-currency values were imported or treated as TWD.

The environment is ready for the next explicitly requested DEV migration phase, but the schema itself is not migration-ready. This report does not authorize or apply migrations.
