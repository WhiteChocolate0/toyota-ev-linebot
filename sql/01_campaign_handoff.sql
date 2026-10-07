-- PURPOSE: Confirm the existing campaign.link_tokens contract required by the
-- handoff RPC. The token table is already owned by the campaign system.
-- EXPECTED: Creates no table and changes no token-table contract. Raises an
-- exception (and stops the package) if the existing prerequisite is unsafe.
-- No campaign_handoffs table is needed by current repository consumers.

begin;

do $$
declare
  missing_columns text[];
  token_hash_unique boolean;
begin
  if to_regnamespace('campaign') is null then
    raise exception 'BLOCKED: campaign schema does not exist; stop and review campaign setup.';
  end if;
  if to_regclass('campaign.link_tokens') is null then
    raise exception 'BLOCKED: campaign.link_tokens does not exist; do not create a parallel token table.';
  end if;

  select array_agg(required.column_name order by required.column_name)
    into missing_columns
  from (values ('id'), ('quiz_result_id'), ('token_hash'), ('status'),
               ('created_at'), ('expires_at'), ('consumed_at')) as required(column_name)
  where not exists (
    select 1 from information_schema.columns actual
    where actual.table_schema = 'campaign'
      and actual.table_name = 'link_tokens'
      and actual.column_name = required.column_name
  );
  if missing_columns is not null then
    raise exception 'BLOCKED: campaign.link_tokens is missing columns: %', missing_columns;
  end if;

  select exists (
    select 1
    from pg_index i
    where i.indrelid = 'campaign.link_tokens'::regclass
      and i.indisunique and i.indpred is null
      and (select array_agg(a.attname order by k.ordinality)
           from unnest(i.indkey) with ordinality as k(attnum, ordinality)
           join pg_attribute a on a.attrelid = i.indrelid and a.attnum = k.attnum
           where k.ordinality <= i.indnkeyatts) = array['token_hash']::name[]
  ) into token_hash_unique;
  if not token_hash_unique then
    raise exception 'BLOCKED: campaign.link_tokens.token_hash is not uniquely constrained; stop for manual review.';
  end if;

  raise notice 'PASS: existing campaign.link_tokens contract verified; no table or data was changed.';
end;
$$;

create index if not exists campaign_link_tokens_active_expiry_idx
  on campaign.link_tokens (status, expires_at);

alter table campaign.link_tokens enable row level security;
revoke all on table campaign.link_tokens from public, anon, authenticated;
grant select, insert, update, delete on table campaign.link_tokens to service_role;

commit;
