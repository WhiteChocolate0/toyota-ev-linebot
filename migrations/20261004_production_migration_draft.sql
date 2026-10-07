-- PRODUCTION DRAFT — INTENTIONALLY NON-EXECUTABLE
--
-- This file is the explicit Production migration artifact requested for review.
-- It is deliberately blocked until a human approver has reviewed a fresh
-- Production dry-run, DEV smoke evidence, backups and the exact source schema.
-- Do not replace this guard with the DEV SQL by copy/paste without approval.
--
-- Candidate DDL for review:
--   20261004_dev_001_campaign_reference_internal.sql
--   20261004_dev_002_campaign_handoff_rpc.sql
--
-- Scope if approved: add campaign handoff/reference/internal aggregate tables
-- only. No existing public LINE Bot state table may be moved, renamed, dropped,
-- truncated or backfilled.
do $$
begin
  raise exception 'Production migration blocked: manual approval and fresh production dry-run are required.';
end;
$$;
