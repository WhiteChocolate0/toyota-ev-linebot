# Challenge Site ↔ LINE Bot Integration Contract

Updated: 2026-10-06  
Implementation status: **BLOCKED — canonical RPC body not applied or integration-tested**. Read-only verification confirms MVP schema 21/21 READY and confirms the existing RPC returns legacy `invalid` for an unknown token. No database write or deployment was performed in this phase.

## Architecture and ownership

The Challenge Site owns `campaign.quiz_sessions`, `campaign.quiz_answers`, `campaign.quiz_results`, `campaign.share_results`, and creation of `campaign.link_tokens`. Its server validates the current participant owns the result through `quiz_result_id → quiz_session_id → participant_id` before minting a token. Sessions without verifiable participant ownership are denied. The browser receives a LINE handoff URL and expiry only; it does not receive a separate token/hash field, persist the token, or display/copy it.

The LINE Bot accepts a raw `campaign_token` from LINE's prefilled message or postback through the single `parse_campaign_handoff_token(...)` helper. It rejects group/room sources before repository access, hashes the token server-side with SHA-256, and calls only `consume_campaign_handoff(p_token_hash text)` for campaign access. The Bot does not query `campaign.quiz_answers` or modify campaign results. It writes only a short-lived conversation hint (result ID, persona, minimal summary, received/expiry times, and the small ability-score summary) into Bot-owned context. Persona/summary may shape an opener only; they are not recommendation or EV Fit rules.

Bot-owned conversation state remains inaccessible to Challenge application code. Shared reference tables (`vehicle_profiles`, `knowledge_sources`, `tax_rules`, `energy_prices`) are independent of this handoff and need not be accessed by the Challenge Site. Organizer/internal tables remain Bot backend-only.

## Tables and payload

| Table / contract | Owner | Current fields or behavior |
| --- | --- | --- |
| `campaign.quiz_sessions` | Challenge | Session ownership is checked through `participant_id`. |
| `campaign.quiz_answers` | Challenge only | Never read by Bot handoff. |
| `campaign.quiz_results` | Challenge; RPC reads minimal result | `id`, `quiz_session_id`, `persona_key`, `ability_scores_json`, `result_summary` (plus other quiz fields not handed to Bot). |
| `campaign.share_results` | Challenge | Share flow only; not used for LINE handoff. |
| `campaign.link_tokens` | Challenge creates; RPC consumes | `id`, `quiz_result_id`, `token_hash`, `status`, `created_at`, `expires_at`, `consumed_at`; no raw token stored. |
| Application success DTO | Bot | `CampaignHandoffResult { quiz_result_id, persona_key, ability_scores, result_summary }`; summary is whitelisted to short `persona_name` and `conversation_hint`. |

The live RPC's legacy success keys are `campaign_result_id`, `persona_key`, `ability_scores_json`, and `result_summary`. The Bot adapter maps the first two legacy names to canonical application keys `quiz_result_id` and `ability_scores`. `result_summary` is normalized rather than copied wholesale. Raw token and token hash are not persisted to context or logs.

## Token lifecycle and LINE link

1. Challenge API verifies participant ownership, generates 32 cryptographically random bytes (base64url raw token), stores only lowercase SHA-256 hex in `campaign.link_tokens.token_hash`, and sets a 15-minute expiry.
2. API responds `{ handoffUrl, expiresAt }`. `handoffUrl` is a LINE OA message URL carrying `campaign_token=<RAW_TOKEN>` as prefilled compose text. `LINE_OA_BASIC_ID` must be configured server-side; invalid/missing configuration is rejected before token creation.
3. The user opens the OA chat and explicitly sends the prefilled message; opening a link alone does not deliver a token to the Bot.
4. Bot parser accepts the delivered text/postback, hashes the raw token, then calls the existing RPC signature. It never puts raw token/hash in user context.
5. The RPC is responsible for locking and atomically consuming an active, unexpired, unused token. A second attempt is rejected.

## RPC and canonical errors

RPC signature remains `public.consume_campaign_handoff(p_token_hash text)`. Canonical application statuses are `SUCCESS`, `TOKEN_NOT_FOUND`, `TOKEN_EXPIRED`, `TOKEN_ALREADY_CONSUMED`, `RESULT_NOT_FOUND`, and `HANDOFF_UNAVAILABLE`. The repository adapter maps current legacy statuses and keys; it never passes `invalid` or database errors to conversation code. The proposed function-body-only update is in `sql/apply_campaign_handoff_rpc_body.sql`; it changes no table or signature and distinguishes missing token from missing result. **It has not been applied.** A read-only random-hash probe of the live MVP RPC returned `invalid`, so the deployed function still cannot distinguish `TOKEN_NOT_FOUND` from `RESULT_NOT_FOUND`.

User-facing copy is intentionally code-free: not found → 「這個活動結果連結無法使用，可以重新完成挑戰後再試一次。」; expired → 「這份活動結果連結已失效，可以重新完成挑戰後再帶結果過來。」; consumed in the same context → 「這份結果已經帶進來了。」; consumed elsewhere/result absent → suggest regenerating or completing the challenge again. Group/room handoff replies 「活動結果請到與電車解惑所的 1 對 1 聊天中開啟，避免把個人測驗結果貼在群組裡。」 and does not call the RPC.

## Security boundary and accepted risk

- Challenge repository exposes no Bot-state query/write path; Bot campaign repository exposes only the handoff RPC.
- `campaign.link_tokens` stores only a digest; raw token is short-lived, single-use, and not logged by the handoff path.
- Challenge verifies session/result ownership server-side; a result UUID alone grants no access.
- Bot rejects `group`/`room` before consume, does not read answers, and stores only a bounded result hint with a 30-minute context expiry.
- `MVP_ACCEPTED_RISK`: both backends currently use Supabase service-role credentials, so DB grants do not fully isolate their server-side authority. Before formal production, replace this with least-privilege DB roles and/or RPC-only access for the Bot.

## Integration test cases

1. Owned result → token created; foreign result → 403 and no insert.
2. Response contains `handoffUrl`/`expiresAt`, not a separate token; DB stores only a 64-character SHA-256 hex digest; raw token is not logged.
3. Expiry is 15 minutes; missing/invalid OA ID fails before token creation.
4. LINE prefilled `campaign_token` text and postback parse to the same raw token; Bot hashes it and maps RPC output to the canonical DTO.
5. Private valid token → minimal context hint; no raw token/hash/answers/session data are saved.
6. Group or room token → privacy reply, consume RPC not called, token remains usable.
7. Second consume, expired, invalid, missing result → canonical internal status and friendly user-facing copy.
8. Challenge code has no Bot state mutation; Bot handoff repository has no quiz-answer query or campaign table CRUD.

## Verification status

Read-only schema verification this phase: **21/21 READY**; environment safety: PASS (`development`, project `extkwpghjfttamontqkl`). RPC apply and DB fixture tests are **NOT RUN**. Supabase CLI is authenticated as an account whose project listing does not include the target MVP project, and no direct database URL/password is configured. Therefore no database write was attempted. To continue, grant the CLI account access to `extkwpghjfttamontqkl` or provide an approved direct DB connection; then apply the standalone SQL, run disposable fixtures (including concurrent consume), clean them up, and verify. No Challenge Site changes or Bot deployment were performed.
