# MVP Manual Migration Package — Schema Contract Review

## 2026-10-06 RPC Apply / Integration Verification Update

**Status: BLOCKED.** Read-only verification against project `extkwpghjfttamontqkl`
passed for all required schema components (21/21 READY). Environment safety
passed as `APP_ENV=development`, `DATABASE_ROLE=development`. The existing
`public.consume_campaign_handoff(p_token_hash text)` RPC is reachable, but a
read-only unknown-hash probe returned legacy status `invalid`; the canonical
error implementation is therefore not yet applied.

The function-body-only SQL is prepared at
`sql/apply_campaign_handoff_rpc_body.sql`. It preserves the function name,
parameter signature, and `campaign.link_tokens` schema. It has **not** been
executed. No fixtures were inserted and no database data was modified.

Apply was blocked because the authenticated Supabase CLI account's project
list does not include `extkwpghjfttamontqkl`, and no direct Postgres URL or
database password is configured. No attempt was made to bypass this with the
service-role REST API. The requested valid/second/expired/unknown/missing-result
and concurrent-consume DB tests remain NOT RUN; rerun them only after authorized
CLI project access or an approved direct DB connection is available. Bot
targeted tests are recorded in the phase result; no deploy or Challenge Site
change occurred.

| Check | Actual | Status |
| --- | --- | --- |
| Environment guard | development / development / `extkwpghjfttamontqkl` | PASS |
| Required schema | 21 required components ready | PASS |
| RPC reachable | `consume_campaign_handoff(text)` callable | PASS |
| Unknown-token RPC status | `invalid` (legacy contract) | BLOCKED |
| Canonical RPC body applied | Not applied | BLOCKED |
| RPC DB integration fixtures | Not run; no authorized write route | BLOCKED |
| Fixture cleanup | No fixtures created | N/A |

The prior manual migration review below is historical context; its `TO_APPLY`
entries reflect the earlier pre-migration state, not the current 21/21 schema
check above.

Date: 2026-10-05

## Status: MANUAL PACKAGE PREPARED; NOT APPLIED

Target: `extkwpghjfttamontqkl` (MVP / DEVELOPMENT). This turn only prepared
SQL files and documentation. No SQL was executed, no fixture was written, no
organizer data was imported, no state table was changed, and no deployment was
performed.

## Campaign handoff decision: REMOVE_CAMPAIGN_HANDOFFS_REQUIREMENT

Code review found that `LinebotRepository.consume_campaign_token()` calls the
atomic RPC and returns the result summary; `EventProcessor` stores that summary
in the user's short-lived `conversation_contexts` slots. No model, repository
method, or service reads a `campaign_handoffs` table. Single-use state already
belongs to `campaign.link_tokens.status` and `consumed_at`. Therefore the
schema checker no longer requires `public.campaign_handoffs`, and the prepared
RPC does not write a redundant handoff row. `campaign_handoffs`, if present
from an unrelated/older design, is only reported by preflight and is not
modified or deleted.

## Current contract and prepared result

| Component | Required contract | Pre-migration actual | Package action | Status |
| --- | --- | --- | --- | --- |
| `campaign.link_tokens` | Existing seven columns; unique `token_hash`; active-expiry index | Table and required columns reachable; index/uniqueness catalog was not available in the prior audit | Assert existing contract; add only active-expiry index if missing; do not create/alter token table | PRECONDITION |
| `public.campaign_handoffs` | Not required | Absent in previous audit | Remove readiness requirement; no create/drop | NOT_REQUIRED |
| `public.consume_campaign_handoff(p_token_hash text)` | One arg, hashed token only; atomic status/expiry/consume; result summary | Missing from PostgREST OpenAPI | Add one RPC; row lock plus conditional update; no quiz_answers read | TO_APPLY |
| `public.tax_rules` | Current repo filter `effective_to`; rule JSON/provenance | Missing | Create table/index; service-role SELECT only | TO_APPLY |
| `public.energy_prices` | Current repo filter `effective_to`; energy/scenario/price/unit/provenance | Missing | Create table/index; service-role SELECT only | TO_APPLY |
| `public.internal_research_sources` | Import source registry and source FK parent | Missing | Create, RLS/backend-only | TO_APPLY |
| `public.internal_concern_priorities` | `LinebotRepository.list_internal_concern_priorities` | Missing | Create with source FK, ordering index and importer unique key | TO_APPLY |
| `public.internal_vehicle_alias_mappings` | Organizer aggregate importer | Missing | Create with source/vehicle FKs and importer unique key | TO_APPLY |
| `public.internal_vehicle_service_benchmarks` | Importer and internal insights repository | Missing | Create with source/vehicle FKs, cohort index, unique key and A-currency/sample-size checks | TO_APPLY |

Four internal table names are derived from importer, repository and service
references in code. Internal source tables are not added to public RAG;
`SharedReferenceRepository` reads only `knowledge_sources`, and the existing
retriever filters sources to public/official visibility.

## Files prepared

- `sql/manual_migration_00_preflight.sql`
- `sql/01_campaign_handoff.sql`
- `sql/02_reference_tables.sql`
- `sql/03_internal_tables.sql`
- `sql/04_consume_campaign_handoff_rpc.sql`
- `sql/05_rls_permissions.sql`
- `sql/06_post_migration_verify.sql`
- `docs/manual_migration_runbook.md`

The SQL contains no drop, truncate, table rename, schema move, raw CDP import,
or Bot state alteration. Internal tables have RLS with client-role access
revoked and service-role access granted. Reference tables are service-role
read-only. RPC permissions are service-role-only.

The old `supabase/linebot_001_shared_boundary.sql` is excluded because it is a
historical state-move draft and uses the superseded
`campaign.campaign_link_tokens` contract; it must not be run for this package.

## Local tests

Python compile and targeted local tests passed: **21 passed** (environment
safety, repository token hashing, organizer/RAG boundaries). These are not
database integration tests. The SQL package has not been run or validated by a
live PostgreSQL parser; Step 6 in the runbook provides read-only live catalog
verification after manual execution.
