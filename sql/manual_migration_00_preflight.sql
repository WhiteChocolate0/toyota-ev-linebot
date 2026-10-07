-- PURPOSE: Read-only preflight for the MVP / DEVELOPMENT migration package.
-- EXPECTED: Metadata rows only. This script does not create or change objects.
-- Stop if campaign.link_tokens is missing required columns or lacks a unique
-- token_hash index. campaign_handoffs is reported for information only.

-- 1. Required schema/table presence before starting.
with expected(schema_name, table_name, required_before_migration, managed_by_package) as (
  values
    ('campaign', 'link_tokens', true, false),
    ('campaign', 'quiz_results', true, false),
    ('public', 'vehicle_profiles', true, false),
    ('public', 'knowledge_sources', true, false),
    ('public', 'campaign_handoffs', false, false),
    ('public', 'tax_rules', false, true),
    ('public', 'energy_prices', false, true),
    ('public', 'internal_research_sources', false, true),
    ('public', 'internal_concern_priorities', false, true),
    ('public', 'internal_vehicle_alias_mappings', false, true),
    ('public', 'internal_vehicle_service_benchmarks', false, true)
)
select e.schema_name,
       e.table_name,
       e.required_before_migration,
       e.managed_by_package,
       (to_regnamespace(e.schema_name) is not null) as schema_exists,
       (to_regclass(format('%I.%I', e.schema_name, e.table_name)) is not null) as table_exists,
       case
         when to_regclass(format('%I.%I', e.schema_name, e.table_name)) is not null then 'EXISTS'
         when e.required_before_migration then 'BLOCKED_MISSING_PREREQUISITE'
         when e.managed_by_package then 'EXPECTED_TO_BE_CREATED'
         else 'NOT_REQUIRED_OR_OUT_OF_SCOPE'
       end as status
from expected e
order by e.schema_name, e.table_name;

-- 2. Existing campaign.link_tokens columns and missing required columns.
with required(column_name) as (
  values ('id'), ('quiz_result_id'), ('token_hash'), ('status'),
         ('created_at'), ('expires_at'), ('consumed_at')
), actual as (
  select column_name
  from information_schema.columns
  where table_schema = 'campaign' and table_name = 'link_tokens'
)
select coalesce(array_agg(a.column_name order by a.ordinal_position), array[]::text[]) as actual_columns,
       coalesce((select array_agg(r.column_name order by r.column_name)
                 from required r left join actual a using (column_name)
                 where a.column_name is null), array[]::text[]) as missing_required_columns
from information_schema.columns a
where a.table_schema = 'campaign' and a.table_name = 'link_tokens';

-- 2b. Types/nullability for existing IDs and the foreign-key type used by the
-- internal alias/benchmark tables. Expected: vehicle_profiles.id is uuid and
-- link_tokens.quiz_result_id matches quiz_results.id.
select table_schema, table_name, column_name, data_type, udt_name, is_nullable
from information_schema.columns
where (table_schema, table_name, column_name) in (
  ('campaign','link_tokens','id'),
  ('campaign','link_tokens','quiz_result_id'),
  ('campaign','quiz_results','id'),
  ('public','vehicle_profiles','id')
)
order by table_schema, table_name, column_name;

-- 3. Existing indexes and unique token_hash check.
select i.indexname, i.indexdef
from pg_indexes i
where i.schemaname = 'campaign' and i.tablename = 'link_tokens'
order by i.indexname;

select idx.relname as index_name, i.indisvalid as index_valid, i.indisready as index_ready,
       i.indisunique as is_unique
from pg_index i
join pg_class t on t.oid=i.indrelid
join pg_namespace n on n.oid=t.relnamespace
join pg_class idx on idx.oid=i.indexrelid
where n.nspname='campaign' and t.relname='link_tokens'
order by idx.relname;

select exists (
  select 1
  from pg_index i
  join pg_class t on t.oid = i.indrelid
  join pg_namespace n on n.oid = t.relnamespace
  where n.nspname = 'campaign' and t.relname = 'link_tokens'
    and i.indisunique and i.indisvalid and i.indisready and i.indpred is null
    and (select array_agg(a.attname order by k.ordinality)
         from unnest(i.indkey) with ordinality as k(attnum, ordinality)
         join pg_attribute a on a.attrelid = t.oid and a.attnum = k.attnum
         where k.ordinality <= i.indnkeyatts) = array['token_hash']::name[]
) as token_hash_is_unique;

-- 4. Existing handoff RPC signature, if any.
select 'public.consume_campaign_handoff(text)' as expected_signature,
       (lookup.function_oid is not null) as rpc_exists,
       coalesce(pg_get_function_identity_arguments(p.oid), 'MISSING') as actual_arguments
from (select to_regprocedure('public.consume_campaign_handoff(text)') as function_oid) lookup
left join pg_proc p on p.oid = lookup.function_oid;

-- 5. Location of existing Bot state tables. This package must leave these rows
-- and tables in place; expected current location is public.
with state_table(table_name) as (
  values ('conversation_contexts'), ('conversation_flows'),
         ('vehicle_preference_profiles'), ('vehicle_comparison_sessions'),
         ('cost_calculations'), ('cost_scenarios'), ('recent_user_results'),
         ('group_member_bot_profiles')
)
select s.table_name,
       coalesce(string_agg(n.nspname, ', ' order by n.nspname), 'MISSING') as actual_schemas
from state_table s
left join pg_class c on c.relname = s.table_name and c.relkind in ('r', 'p')
left join pg_namespace n on n.oid = c.relnamespace
group by s.table_name
order by s.table_name;
