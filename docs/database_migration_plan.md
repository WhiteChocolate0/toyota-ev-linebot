# Database Migration Plan

## Phase 1 — DEV schema

Apply only on a non-Production DEV project:

1. `migrations/20261004_dev_001_campaign_reference_internal.sql`
2. `migrations/20261004_dev_002_campaign_handoff_rpc.sql`

These create the missing campaign token contract, `public.tax_rules`, `public.energy_prices`, `public.internal_*` aggregate tables, and the atomic handoff RPC. They do not alter existing Bot state tables.

## Phase 2 — DEV aggregate import

Run `scripts/import_organizer_aggregates.py --apply` only after the two SQL files. It imports only concern priorities, aliases, and aggregate benchmarks. Raw CDP rows are never uploaded.

## Phase 3 — DEV validation

Run schema readiness, shared/reference reads, internal reads, campaign create/consume smoke tests, RAG isolation tests, then conversation regression. P0 product failures must be zero.

## Phase 4 — Production dry run

Use a correctly configured Production read-only process to audit the exact schema, repository contract and API schema exposure. Do not run SQL or import data in this phase.

## Phase 5 — manual Production approval

Only after DEV evidence and a named owner approval may an equivalent Production migration be created and applied. It must include a backup, maintenance window, smoke test and rollback decision. No `ALTER TABLE ... SET SCHEMA`, rename, drop, truncate or raw CDP backfill is included in this plan.

`migrations/20261004_production_migration_draft.sql` is intentionally non-executable and exists for review only. The approved Production DDL must be regenerated from the DEV-proven files against a fresh Production contract; it must not be applied by an automated deploy.
