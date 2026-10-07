-- DEV ONLY. Requires 20261004_dev_001_campaign_reference_internal.sql.
-- Atomic single-use handoff: receives only the SHA-256 hex digest, not the
-- bearer token. Reads quiz_results summary only, never quiz_answers.
begin;

create or replace function public.consume_campaign_handoff(p_token_hash text)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public, campaign, pg_temp
as $$
declare
  token_row campaign.link_tokens%rowtype;
  result_row campaign.quiz_results%rowtype;
begin
  if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$' then
    return jsonb_build_object('status', 'TOKEN_NOT_FOUND');
  end if;
  select * into token_row from campaign.link_tokens
  where token_hash = p_token_hash for update;
  if not found then return jsonb_build_object('status', 'TOKEN_NOT_FOUND'); end if;
  if token_row.status = 'consumed' or token_row.consumed_at is not null then return jsonb_build_object('status', 'TOKEN_ALREADY_CONSUMED', 'campaign_result_id', token_row.quiz_result_id); end if;
  if token_row.status <> 'active' then return jsonb_build_object('status', 'TOKEN_NOT_FOUND'); end if;
  if token_row.expires_at <= now() then
    update campaign.link_tokens set status = 'expired' where id = token_row.id;
    return jsonb_build_object('status', 'TOKEN_EXPIRED');
  end if;
  select * into result_row from campaign.quiz_results where id = token_row.quiz_result_id;
  if not found then return jsonb_build_object('status', 'RESULT_NOT_FOUND'); end if;
  update campaign.link_tokens
     set status = 'consumed', consumed_at = now()
   where id = token_row.id and status = 'active' and consumed_at is null;
  if not found then return jsonb_build_object('status', 'TOKEN_ALREADY_CONSUMED', 'campaign_result_id', token_row.quiz_result_id); end if;
  return jsonb_build_object('status', 'ok', 'campaign_result_id', result_row.id, 'persona_key', result_row.persona_key, 'ability_scores_json', result_row.ability_scores_json, 'result_summary', result_row.result_summary);
end;
$$;

revoke all on function public.consume_campaign_handoff(text) from public, anon, authenticated;
grant execute on function public.consume_campaign_handoff(text) to service_role;

-- Read-only schema metadata used by scripts/check_db_schema.py. This returns
-- names and catalog metadata only; it cannot read table rows.
create or replace function public.dev_schema_contract()
returns jsonb
language sql
security definer
set search_path = pg_catalog
as $$
  select jsonb_build_object(
    'schemas', coalesce((
      select jsonb_agg(nspname order by nspname)
      from pg_namespace
      where nspname in ('public', 'campaign')
    ), '[]'::jsonb),
    'tables', coalesce((
      select jsonb_agg(jsonb_build_object(
        'schema', n.nspname,
        'table', c.relname,
        'columns', coalesce((
          select jsonb_agg(a.attname order by a.attnum)
          from pg_attribute a
          where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
        ), '[]'::jsonb),
        'indexes', coalesce((
          select jsonb_agg(jsonb_build_object(
            'name', idx.relname,
            'unique', i.indisunique,
            'valid', i.indisvalid,
            'ready', i.indisready,
            'columns', coalesce((
              select jsonb_agg(att.attname order by k.ordinality)
              from unnest(i.indkey) with ordinality as k(attnum, ordinality)
              join pg_attribute att on att.attrelid = c.oid and att.attnum = k.attnum
              where k.ordinality <= i.indnkeyatts
            ), '[]'::jsonb)
          ) order by idx.relname)
          from pg_index i
          join pg_class idx on idx.oid = i.indexrelid
          where i.indrelid = c.oid
        ), '[]'::jsonb),
        'foreign_keys', coalesce((
          select jsonb_agg(jsonb_build_object(
            'name', con.conname,
            'validated', con.convalidated,
            'columns', (select jsonb_agg(a.attname order by k.ordinality)
              from unnest(con.conkey) with ordinality as k(attnum, ordinality)
              join pg_attribute a on a.attrelid = c.oid and a.attnum = k.attnum),
            'target_schema', target_ns.nspname,
            'target_table', target.relname,
            'target_columns', (select jsonb_agg(ta.attname order by tk.ordinality)
              from unnest(con.confkey) with ordinality as tk(attnum, ordinality)
              join pg_attribute ta on ta.attrelid = target.oid and ta.attnum = tk.attnum),
            'delete_action', con.confdeltype
          ) order by con.conname)
          from pg_constraint con
          join pg_class target on target.oid = con.confrelid
          join pg_namespace target_ns on target_ns.oid = target.relnamespace
          where con.conrelid = c.oid and con.contype = 'f'
        ), '[]'::jsonb),
        'rls_enabled', c.relrowsecurity,
        'access', jsonb_build_object(
          'anon_select', has_table_privilege('anon', c.oid, 'SELECT'),
          'anon_insert', has_table_privilege('anon', c.oid, 'INSERT'),
          'anon_update', has_table_privilege('anon', c.oid, 'UPDATE'),
          'anon_delete', has_table_privilege('anon', c.oid, 'DELETE'),
          'authenticated_select', has_table_privilege('authenticated', c.oid, 'SELECT'),
          'authenticated_insert', has_table_privilege('authenticated', c.oid, 'INSERT'),
          'authenticated_update', has_table_privilege('authenticated', c.oid, 'UPDATE'),
          'authenticated_delete', has_table_privilege('authenticated', c.oid, 'DELETE'),
          'service_role_select', has_table_privilege('service_role', c.oid, 'SELECT'),
          'service_role_insert', has_table_privilege('service_role', c.oid, 'INSERT'),
          'service_role_update', has_table_privilege('service_role', c.oid, 'UPDATE'),
          'service_role_delete', has_table_privilege('service_role', c.oid, 'DELETE')
        )
      ) order by n.nspname, c.relname)
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      where c.relkind in ('r', 'p') and (
        (n.nspname = 'campaign' and c.relname in ('link_tokens','quiz_sessions','quiz_answers','quiz_results','share_results'))
        or (n.nspname = 'public' and c.relname in ('tax_rules','energy_prices','internal_research_sources','internal_concern_priorities','internal_vehicle_alias_mappings','internal_vehicle_service_benchmarks','vehicle_profiles','knowledge_sources'))
      )
    ), '[]'::jsonb),
    'functions', coalesce((
      select jsonb_agg(jsonb_build_object(
        'name', p.proname,
        'args', pg_get_function_identity_arguments(p.oid),
        'anon_execute', has_function_privilege('anon', p.oid, 'EXECUTE'),
        'authenticated_execute', has_function_privilege('authenticated', p.oid, 'EXECUTE'),
        'service_role_execute', has_function_privilege('service_role', p.oid, 'EXECUTE')
      ) order by p.proname)
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public' and p.proname in ('consume_campaign_handoff', 'dev_schema_contract')
    ), '[]'::jsonb)
  );
$$;
revoke all on function public.dev_schema_contract() from public, anon, authenticated;
grant execute on function public.dev_schema_contract() to service_role;

notify pgrst, 'reload schema';
commit;
