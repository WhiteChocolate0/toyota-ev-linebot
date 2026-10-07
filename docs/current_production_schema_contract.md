# Current Production Schema Contract

日期：2026-10-04。此文件記錄最近一次唯讀 Production audit 的實際狀態，優先於 README 的長期理想架構。

## Runtime contract

現有 Production Bot state 位於 `public`。`BOT_STATE_SCHEMA=public` 是競賽期間的相容設定；repository 對非 shared table 會使用它，不再硬編碼 `linebot`。因此 public state tables 是 `LEGACY_BUT_COMPATIBLE`，不需要搬移。

| 區域 | 已觀測／使用的資料表 |
| --- | --- |
| `public` state | `conversation_contexts`, `conversation_flows`, `vehicle_preference_profiles`, `vehicle_comparison_sessions`, `cost_calculations`, `cost_scenarios`, `recent_user_results`, `group_member_bot_profiles`, `groups`, `concerns`, `conversation_events`, `group_member_signals`, `group_concern_board`, `group_summaries` |
| `public` shared | `vehicle_profiles`, `vehicle_specifications`, `vehicle_features`, `knowledge_sources`, `reference_parameters` |
| `campaign` | `quiz_sessions`, `quiz_answers`, `quiz_results`, `share_results`, `link_tokens` |

## Current gaps

- `campaign.link_tokens` is the token contract; `public.consume_campaign_handoff` still requires verification in DEV.
- `public.tax_rules` and `public.energy_prices` are absent.
- Internal organizer aggregate tables are absent.
- `linebot` schema is not exposed, but this is not a blocker while `BOT_STATE_SCHEMA=public` is the explicit runtime contract.

## Repository routing

- shared official references: always `public`, read-only in normal chat.
- Bot state: `BOT_STATE_SCHEMA` (currently `public`).
- internal organizer aggregates: `public.internal_*`, service-role only, never RAG.
- campaign handoff: only the atomic `public.consume_campaign_handoff` RPC; no repository method reads `quiz_answers`.

Any future move to `linebot` is a separately approved state migration with backup, compatibility window, smoke test and rollback plan; it is not part of this release.
