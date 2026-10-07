# MVP / DEVELOPMENT database migration package

For this manual Supabase Dashboard workflow, the canonical ordered package is
the set of SQL files under `sql/`, documented in
`docs/manual_migration_runbook.md`. Run preflight first and stop on any error
or `BLOCKED` result. The SQL package has not been applied by the assistant.

The existing `20261004_dev_001_campaign_reference_internal.sql` and
`20261004_dev_002_campaign_handoff_rpc.sql` remain DEV-only migration drafts;
do not apply both those drafts and the split manual package. Both use the
existing `campaign.link_tokens` contract, not a parallel
`campaign.campaign_link_tokens` table, and leave Bot state in `public`.

`campaign_handoffs` is intentionally not required. The current repository
returns the quiz summary from the atomic RPC and stores it in the user's
short-lived conversation context; `campaign.link_tokens` already persists
single-use status. The RPC receives only a SHA-256 digest in `p_token_hash`.

Do **not** run `supabase/linebot_001_shared_boundary.sql` as part of this MVP
package. It is a historical draft for moving state to `linebot` and references
the superseded campaign token table name.

The MVP database must not be automatically promoted to Production. A future
Production project requires a separately reviewed/exported migration and
deployment flow. No Production project/key belongs in this DEV workflow.
