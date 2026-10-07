# DEV Readiness Report

日期：2026-10-04

## Status: BLOCKED

| Severity | Component | Reason | Required action |
| --- | --- | --- | --- |
| P0 | Environment isolation | `APP_ENV=development` currently resolves to Production project ref `extkwpghjfttamontqkl`. | Configure a dedicated DEV Supabase URL/project ref. |
| P0 | DEV migration | No safe DEV project is configured, so the generated DEV-only SQL was not applied. | Configure DEV, then run the two migrations in order. |
| P0 | DEV aggregate import | The guarded importer correctly refuses the current connection. No aggregate was imported. | Apply DEV migration then run the importer on DEV only. |
| P0 | Conversation regression | 80 golden scenarios: 44 passed, 36 failed; report includes 1 `INTENT` failure and 51 `COPY` assertions. | Resolve P0 behavior/spec failures and rerun until product failures are zero. |

## Completed locally

- Environment safety unit tests and organizer-data boundary tests pass.
- Targeted suite: 50 passed (`environment_safety`, organizer isolation, router, RAG, EV Fit, cost flow, context).
- CDP offline processing remains complete: 1,051,612 raw rows, 3,368 exact duplicates removed before aggregation, 1,048,244 deduplicated rows.
- No Production write, migration, seed, import or deploy occurred.

## DEV smoke tests pending

The following must run after a DEV project is available and the DEV migrations are applied: shared vehicle/knowledge/tax/energy reads; internal priority/benchmark reads; RAG rejection of internal rows; anonymous currency rendering guard; demographic exclusion; small-sample/ambiguous mapping gates; and create/consume/expired campaign token checks.

## Production state table decision

Existing Bot state tables remaining in `public` are treated as `LEGACY_BUT_COMPATIBLE` with `BOT_STATE_SCHEMA=public`. They are not a readiness blocker and will not be moved in this phase.
