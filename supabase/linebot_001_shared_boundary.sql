-- Shared PROD boundary for the campaign site and LINE Bot.
-- Run after 028.  Campaign owns its tables and must apply its schema before
-- the RPC at the end of this file is created.

create schema if not exists linebot;
create schema if not exists campaign;

-- Keep official reference data in public/shared.  No linebot_* catalogue is
-- created: both products read vehicle_profiles, knowledge_sources, tax_rules,
-- energy_prices, reference_parameters, vehicle_features and specifications.
alter table public.groups set schema linebot;
alter table public.webhook_events set schema linebot;
alter table public.conversation_events set schema linebot;
alter table public.concerns set schema linebot;
alter table public.group_summaries set schema linebot;
alter table public.group_member_signals set schema linebot;
alter table public.group_member_bot_profiles set schema linebot;
alter table public.group_concern_board set schema linebot;
alter table public.conversation_contexts set schema linebot;
alter table public.conversation_flows set schema linebot;
alter table public.bot_sessions set schema linebot;
alter table public.vehicle_preference_profiles set schema linebot;
alter table public.vehicle_comparison_sessions set schema linebot;
alter table public.cost_calculations set schema linebot;
alter table public.cost_scenarios set schema linebot;
alter table public.recent_user_results set schema linebot;
alter table public.private_user_bot_profiles set schema linebot;
alter table public.knowledge_gap_logs set schema linebot;

create table if not exists linebot.ev_fit_results (
  id uuid primary key default gen_random_uuid(),
  user_id_hash text not null,
  group_id uuid references linebot.groups(id) on delete set null,
  result_json jsonb not null,
  completed_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index if not exists ev_fit_results_user_completed_idx
  on linebot.ev_fit_results (user_id_hash, completed_at desc);

create table if not exists linebot.campaign_handoffs (
  id uuid primary key default gen_random_uuid(),
  user_id_hash text not null,
  campaign_result_id uuid not null,
  persona_key text,
  result_summary text,
  received_at timestamptz not null default now(),
  expires_at timestamptz not null,
  unique (user_id_hash, campaign_result_id)
);

alter table linebot.ev_fit_results enable row level security;
alter table linebot.campaign_handoffs enable row level security;

-- No browser role is granted access to linebot state.  Backend service-role
-- bypasses RLS; the campaign website must not receive that credential.
revoke all on all tables in schema linebot from anon, authenticated;
revoke all on schema linebot from anon, authenticated;

-- Campaign-owned prerequisite tables:
-- campaign.campaign_link_tokens(token_hash, quiz_result_id, expires_at, consumed_at)
-- campaign.quiz_results(id, persona_key, ability_scores_json, result_summary)
-- Token plaintext is never stored; callers pass a random one-time token.
create or replace function public.consume_campaign_handoff(
  p_token text,
  p_user_id_hash text
) returns table(status text, campaign_result_id uuid, persona_key text,
                ability_scores_json jsonb, result_summary text)
language plpgsql security definer set search_path = public, campaign, linebot, pg_temp
as $$
declare
  token_row campaign.campaign_link_tokens%rowtype;
  result_row campaign.quiz_results%rowtype;
begin
  select * into token_row
  from campaign.campaign_link_tokens
  where token_hash = encode(digest(p_token, 'sha256'), 'hex')
  for update;

  if not found then
    return query select 'invalid'::text, null::uuid, null::text, null::jsonb, null::text;
    return;
  end if;
  if token_row.expires_at <= now() then
    return query select 'expired'::text, null::uuid, null::text, null::jsonb, null::text;
    return;
  end if;
  if token_row.consumed_at is not null then
    return query select 'consumed'::text, token_row.quiz_result_id, null::text, null::jsonb, null::text;
    return;
  end if;

  select * into result_row from campaign.quiz_results where id = token_row.quiz_result_id;
  if not found then
    return query select 'invalid'::text, null::uuid, null::text, null::jsonb, null::text;
    return;
  end if;

  update campaign.campaign_link_tokens set consumed_at = now() where token_hash = token_row.token_hash;
  insert into linebot.campaign_handoffs (user_id_hash, campaign_result_id, persona_key, result_summary, expires_at)
  values (p_user_id_hash, result_row.id, result_row.persona_key, result_row.result_summary, now() + interval '7 days')
  on conflict (user_id_hash, campaign_result_id) do nothing;

  return query select 'ok'::text, result_row.id, result_row.persona_key,
                      result_row.ability_scores_json, result_row.result_summary;
end;
$$;

revoke all on function public.consume_campaign_handoff(text, text) from public, anon, authenticated;
