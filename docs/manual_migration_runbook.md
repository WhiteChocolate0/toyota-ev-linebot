# MVP / DEVELOPMENT Manual Migration Runbook

Target project: `extkwpghjfttamontqkl` (MVP / DEVELOPMENT only)

These SQL files are a copy/paste package for **Supabase Dashboard → SQL Editor**.
They are prepared for the user to run manually. No SQL in this runbook has been
executed by the assistant. Do not select a future Production project here.
Do not run the historical `supabase/linebot_001_shared_boundary.sql`; it
references the superseded `campaign.campaign_link_tokens` name and attempts a
Bot state schema move, both outside this package.

## Design decisions

- **REMOVE_CAMPAIGN_HANDOFFS_REQUIREMENT.** The current repository gets the
  result summary from `consume_campaign_handoff` and writes it to the user's
  short-lived `conversation_contexts` slot. No model, repository method, or
  service reads a `campaign_handoffs` table. `campaign.link_tokens` already
  owns single-use state (`status`, `consumed_at`), so a second handoff table
  would currently have no consumer and duplicate some lifecycle data. The
  preflight reports whether an old `public.campaign_handoffs` table happens to
  exist but does not require, create, or delete it.
- The four internal tables are code-derived: `internal_research_sources`
  (organizer importer/source FK parent), `internal_concern_priorities`
  (`LinebotRepository.list_internal_concern_priorities`),
  `internal_vehicle_alias_mappings` (aggregate importer), and
  `internal_vehicle_service_benchmarks` (aggregate importer plus internal
  insights repository).
- Reference queries currently filter on `effective_to`; the SQL uses that
  column name to match `SharedReferenceRepository`. Bot code reads those
  references through service-role backend access. Normal chat code does not
  write them.
- The RPC accepts only `p_token_hash` (SHA-256 hex). It has no LINE user id
  parameter; the existing Bot context persistence remains responsible for the
  short-lived user context. It locks the token row, validates it, reads only
  `campaign.quiz_results` summary fields, and updates the token within one
  PostgreSQL function transaction. It never reads `campaign.quiz_answers`.

## Internal table contract

All four tables use `visibility='INTERNAL_ORGANIZER'`, RLS enabled, no anon or
authenticated grants/policies, and service-role backend access. They are not
in `knowledge_sources` and are not queried by public RAG.

| Table | Purpose / consumer | Required columns | Indexes / unique keys | RLS boundary |
| --- | --- | --- | --- | --- |
| `internal_research_sources` | Source metadata and FK parent; organizer importer | `id, title, source_kind, snapshot_period, visibility, created_at` | PK `id` | RLS; no client-role privileges; backend CRUD |
| `internal_concern_priorities` | Priority list; `LinebotRepository.list_internal_concern_priorities` | `id, concern_type, priority_rank, weight, research_source_id, snapshot_period, visibility, created_at` | order `(priority_rank, concern_type)`; unique `(research_source_id, concern_type, snapshot_period)` | RLS; no client-role privileges; backend CRUD |
| `internal_vehicle_alias_mappings` | Canonical mapping review/import; organizer aggregate importer | `id, raw_model_name, normalized_model_name, vehicle_id, mapping_status, source_id, snapshot_date, sample_size, visibility` | status/name index; unique `(source_id, raw_model_name, snapshot_date)` | RLS; no client-role privileges; backend CRUD |
| `internal_vehicle_service_benchmarks` | Cohort/sample-gated aggregates; importer and internal insights repository | Vehicle/cohort/sample; service visit metrics; A-currency aggregates; source/date/visibility/status | vehicle/cohort index; unique `(vehicle_id, vehicle_age_bucket, source_id, snapshot_date)` | RLS; no client-role privileges; backend CRUD |

The vehicle alias and benchmark tables reference `public.vehicle_profiles(id)`;
concern, alias and benchmark rows reference `internal_research_sources(id)`.
The benchmark constraint blocks `READY` samples below 30 and requires the
currency marker `ANONYMIZED_A_CURRENCY`.

## Files

1. `sql/manual_migration_00_preflight.sql` — read-only baseline.
2. `sql/01_campaign_handoff.sql` — asserts the existing `campaign.link_tokens`
   contract, adds its expiry lookup index if missing, and reapplies its
   backend-only access boundary. It creates no token or handoff table.
3. `sql/02_reference_tables.sql` — creates `public.tax_rules` and
   `public.energy_prices` with active lookup indexes.
4. `sql/03_internal_tables.sql` — creates the four code-derived internal
   tables, unique keys/upsert targets, foreign keys, sample gate, and indexes.
5. `sql/04_consume_campaign_handoff_rpc.sql` — creates the atomic
   `consume_campaign_handoff(p_token_hash text)` RPC and the service-role-only
   catalog metadata RPC used by `scripts/check_db_schema.py`.
6. `sql/05_rls_permissions.sql` — reapplies RLS and least-privilege grants.
7. `sql/06_post_migration_verify.sql` — read-only final contract verification.

## Execution sequence

Run each complete file in SQL Editor against the `extkwpghjfttamontqkl`
project. Wait for its completion and inspect the result before proceeding.
If any statement errors, any required check says `BLOCKED`, or the editor
reports a transaction failure, **stop there**. Do not continue to the next
file; save the error text and investigate first. Do not rerun a later step to
try to bypass an earlier failure.

### Step 0 — Preflight

Run `sql/manual_migration_00_preflight.sql`.

Expected:

- `campaign` schema, `campaign.link_tokens`, `campaign.quiz_results`,
  `public.vehicle_profiles`, and `public.knowledge_sources` exist.
- `campaign.link_tokens` has all seven expected columns and
  `token_hash_is_unique = true`.
- `campaign.link_tokens.quiz_result_id` has the same DB type as
  `campaign.quiz_results.id`, and `public.vehicle_profiles.id` is UUID (the
  internal vehicle FKs use UUID).
- Bot state location output shows existing state tables in `public`.
- Missing reference/internal tables are reported as expected package targets.
- `campaign_handoffs` is informational only; its absence is not a blocker.
- Existing `consume_campaign_handoff(text)` may be absent before migration.

Stop if the token table/columns/uniqueness, ID types, or required foreign-key
target tables do not match. Do not edit or recreate `campaign.link_tokens` to
force a pass.

### Step 1 — `01_campaign_handoff.sql`

Expected SQL Editor notice: `PASS: existing campaign.link_tokens contract
verified`. The expiry lookup index and restricted access boundary are
reasserted idempotently. No token rows or table columns are changed.

Stop if the script raises a `BLOCKED` exception.

### Step 2 — `02_reference_tables.sql`

Expected: both `public.tax_rules` and `public.energy_prices` exist with their
active lookup indexes. The script also immediately enables RLS and removes
client-role access; `service_role` receives SELECT only.

Stop on any SQL error or constraint/index conflict. Do not seed official data
in this phase.

### Step 3 — `03_internal_tables.sql`

Expected: the four internal tables and importer upsert keys/indexes exist.
RLS and backend-only permissions are applied immediately in this file as well
as reasserted in Step 5. No aggregate benchmark or raw CDP data is inserted.

Stop on any SQL error, especially a foreign-key type mismatch with
`public.vehicle_profiles.id`.

### Step 4 — `04_consume_campaign_handoff_rpc.sql`

Expected: `public.consume_campaign_handoff(p_token_hash text)` and
`public.dev_schema_contract()` are created. The RPC returns `status=ok` for a
successful consume and rejects invalid, expired, or already-consumed tokens.
Only service role may execute either function.

Stop if the function signature or permissions cannot be created. Do not
replace/rename the existing `campaign.link_tokens` contract.

### Step 5 — `05_rls_permissions.sql`

Expected: no anon/authenticated direct access to token, reference, or internal
tables; RLS enabled; backend service role can read/write internal tables and
tokens, but can only read shared reference tables. `public.vehicle_profiles`,
`public.knowledge_sources`, and existing Bot state table definitions are not
changed.

Stop if any grant/revoke fails. This step intentionally creates no permissive
RLS policies for client roles.

### Step 6 — `06_post_migration_verify.sql`

Expected: each table/column/index/unique/FK/RLS/permission/RPC/state-location
row reports `READY`, followed by a final `OVERALL = MVP_SCHEMA_READY` row.
Anything missing or mismatched must report `BLOCKED`; stop and keep the output
for review. The SQL is read-only.

After SQL verification, the local code boundary tests can be run with:

```sh
.venv/bin/python -m pytest -q tests/test_environment_safety.py tests/test_campaign_handoff_repository.py tests/test_organizer_data_boundaries.py
.venv/bin/python scripts/check_db_schema.py --summary
```

The first command verifies local role guards, token hashing at the repository
boundary, and public RAG exclusion of organizer sources. The SQL Editor check
is authoritative for Postgres indexes, foreign keys, RLS and ACLs. This
package does not include RPC data-fixture tests, official reference seeding,
aggregate import, production migration, or deployment.
