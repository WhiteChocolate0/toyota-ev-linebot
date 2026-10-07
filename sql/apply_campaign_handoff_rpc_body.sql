-- Purpose: update only the existing RPC implementation on the MVP/DEV database.
-- Does not create/alter tables, change the function signature, or touch Bot state.
-- Preconditions: APP_ENV=development, DATABASE_ROLE=development,
-- project ref=extkwpghjfttamontqkl; run scripts/check_test_environment.py first.

begin;

do $$
begin
  if to_regclass('campaign.link_tokens') is null
     or to_regclass('campaign.quiz_results') is null then
    raise exception 'BLOCKED: campaign handoff tables are unavailable';
  end if;
  if to_regprocedure('public.consume_campaign_handoff(text)') is null then
    raise exception 'BLOCKED: expected RPC signature public.consume_campaign_handoff(text) is unavailable';
  end if;
end;
$$;

create or replace function public.consume_campaign_handoff(p_token_hash text)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public, campaign, pg_temp
as $$
declare
  token_row campaign.link_tokens%rowtype;
  result_row campaign.quiz_results%rowtype;
  consumed_at_value timestamptz;
begin
  if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$' then
    return jsonb_build_object('status', 'TOKEN_NOT_FOUND');
  end if;

  -- FOR UPDATE serializes attempts on this token until this function's
  -- transaction commits. The raw bearer token never reaches this function.
  select * into token_row
    from campaign.link_tokens
   where token_hash = p_token_hash
   for update;

  if not found then
    return jsonb_build_object('status', 'TOKEN_NOT_FOUND');
  end if;
  if token_row.consumed_at is not null or token_row.status = 'consumed' then
    return jsonb_build_object(
      'status', 'TOKEN_ALREADY_CONSUMED',
      'campaign_result_id', token_row.quiz_result_id
    );
  end if;
  if token_row.status = 'expired' or token_row.expires_at <= now() then
    if token_row.status = 'active' then
      update campaign.link_tokens
         set status = 'expired'
       where id = token_row.id and status = 'active' and consumed_at is null;
    end if;
    return jsonb_build_object('status', 'TOKEN_EXPIRED');
  end if;
  if token_row.status <> 'active' then
    return jsonb_build_object('status', 'TOKEN_NOT_FOUND');
  end if;

  select * into result_row
    from campaign.quiz_results
   where id = token_row.quiz_result_id;
  if not found then
    return jsonb_build_object('status', 'RESULT_NOT_FOUND');
  end if;

  -- Keep the guarded state transition in the same transaction as validation
  -- and result lookup; the row lock plus predicate allows only one success.
  update campaign.link_tokens
     set status = 'consumed', consumed_at = now()
   where id = token_row.id and status = 'active' and consumed_at is null
  returning consumed_at into consumed_at_value;
  if not found then
    return jsonb_build_object(
      'status', 'TOKEN_ALREADY_CONSUMED',
      'campaign_result_id', token_row.quiz_result_id
    );
  end if;

  return jsonb_build_object(
    'status', 'SUCCESS',
    'campaign_result_id', result_row.id,
    'persona_key', result_row.persona_key,
    'ability_scores_json', result_row.ability_scores_json,
    'result_summary', result_row.result_summary
  );
end;
$$;

revoke all on function public.consume_campaign_handoff(text) from public, anon, authenticated;
grant execute on function public.consume_campaign_handoff(text) to service_role;

commit;
