-- PURPOSE: Read-only post-migration verification in Supabase SQL Editor.
-- EXPECTED: One row per contract check plus OVERALL = MVP_SCHEMA_READY or
-- BLOCKED. This file performs no DDL and reads no application rows.

with required_tables(schema_name, table_name) as (
  values
    ('campaign','link_tokens'), ('campaign','quiz_results'),
    ('public','vehicle_profiles'), ('public','knowledge_sources'),
    ('public','tax_rules'), ('public','energy_prices'),
    ('public','internal_research_sources'), ('public','internal_concern_priorities'),
    ('public','internal_vehicle_alias_mappings'), ('public','internal_vehicle_service_benchmarks')
),
table_checks as (
  select 'TABLE ' || schema_name || '.' || table_name as component,
         'table exists'::text as expected,
         case when to_regclass(format('%I.%I', schema_name, table_name)) is null then 'MISSING' else 'EXISTS' end as actual,
         case when to_regclass(format('%I.%I', schema_name, table_name)) is null then 'BLOCKED' else 'READY' end as status,
         ''::text as notes
  from required_tables
),
required_columns(schema_name, table_name, column_name) as (
  values
    ('campaign','link_tokens','id'), ('campaign','link_tokens','quiz_result_id'),
    ('campaign','link_tokens','token_hash'), ('campaign','link_tokens','status'),
    ('campaign','link_tokens','created_at'), ('campaign','link_tokens','expires_at'),
    ('campaign','link_tokens','consumed_at'),
    ('campaign','quiz_results','persona_key'), ('campaign','quiz_results','ability_scores_json'),
    ('campaign','quiz_results','result_summary'),
    ('public','vehicle_profiles','id'), ('public','knowledge_sources','id'),
    ('public','tax_rules','id'), ('public','tax_rules','rule_key'),
    ('public','tax_rules','rule_type'), ('public','tax_rules','vehicle_scope'),
    ('public','tax_rules','value_json'), ('public','tax_rules','effective_from'),
    ('public','tax_rules','effective_to'), ('public','tax_rules','source_id'),
    ('public','tax_rules','source_url'), ('public','tax_rules','source_type'),
    ('public','tax_rules','verified_at'), ('public','tax_rules','created_at'),
    ('public','tax_rules','updated_at'),
    ('public','energy_prices','id'), ('public','energy_prices','energy_type'),
    ('public','energy_prices','scenario_type'), ('public','energy_prices','price_value'),
    ('public','energy_prices','price_unit'), ('public','energy_prices','effective_from'),
    ('public','energy_prices','effective_to'), ('public','energy_prices','source_id'),
    ('public','energy_prices','source_url'), ('public','energy_prices','source_type'),
    ('public','energy_prices','verified_at'), ('public','energy_prices','created_at'),
    ('public','energy_prices','updated_at'),
    ('public','internal_research_sources','id'), ('public','internal_research_sources','title'),
    ('public','internal_research_sources','source_kind'), ('public','internal_research_sources','snapshot_period'),
    ('public','internal_research_sources','visibility'), ('public','internal_research_sources','created_at'),
    ('public','internal_concern_priorities','id'), ('public','internal_concern_priorities','concern_type'),
    ('public','internal_concern_priorities','priority_rank'), ('public','internal_concern_priorities','weight'),
    ('public','internal_concern_priorities','research_source_id'), ('public','internal_concern_priorities','snapshot_period'),
    ('public','internal_concern_priorities','visibility'), ('public','internal_concern_priorities','created_at'),
    ('public','internal_vehicle_alias_mappings','id'), ('public','internal_vehicle_alias_mappings','raw_model_name'),
    ('public','internal_vehicle_alias_mappings','normalized_model_name'), ('public','internal_vehicle_alias_mappings','vehicle_id'),
    ('public','internal_vehicle_alias_mappings','mapping_status'), ('public','internal_vehicle_alias_mappings','source_id'),
    ('public','internal_vehicle_alias_mappings','snapshot_date'), ('public','internal_vehicle_alias_mappings','sample_size'),
    ('public','internal_vehicle_alias_mappings','visibility'),
    ('public','internal_vehicle_service_benchmarks','id'), ('public','internal_vehicle_service_benchmarks','vehicle_id'),
    ('public','internal_vehicle_service_benchmarks','vehicle_age_bucket'), ('public','internal_vehicle_service_benchmarks','sample_size'),
    ('public','internal_vehicle_service_benchmarks','avg_service_visits'), ('public','internal_vehicle_service_benchmarks','median_service_visits'),
    ('public','internal_vehicle_service_benchmarks','avg_paid_service_visits'), ('public','internal_vehicle_service_benchmarks','median_paid_service_visits'),
    ('public','internal_vehicle_service_benchmarks','avg_scheduled_maintenance_visits'), ('public','internal_vehicle_service_benchmarks','median_scheduled_maintenance_visits'),
    ('public','internal_vehicle_service_benchmarks','avg_repair_visits'), ('public','internal_vehicle_service_benchmarks','median_repair_visits'),
    ('public','internal_vehicle_service_benchmarks','avg_service_amount_a_currency'), ('public','internal_vehicle_service_benchmarks','median_service_amount_a_currency'),
    ('public','internal_vehicle_service_benchmarks','avg_maintenance_amount_a_currency'), ('public','internal_vehicle_service_benchmarks','median_maintenance_amount_a_currency'),
    ('public','internal_vehicle_service_benchmarks','currency_type'), ('public','internal_vehicle_service_benchmarks','source_id'),
    ('public','internal_vehicle_service_benchmarks','snapshot_date'), ('public','internal_vehicle_service_benchmarks','visibility'),
    ('public','internal_vehicle_service_benchmarks','status')
),
column_checks as (
  select 'COLUMNS ' || schema_name || '.' || table_name as component,
         string_agg(column_name, ', ' order by column_name) as expected,
         coalesce(string_agg(column_name, ', ' order by column_name) filter (
           where exists (select 1 from information_schema.columns c
                         where c.table_schema = required_columns.schema_name
                           and c.table_name = required_columns.table_name
                           and c.column_name = required_columns.column_name)
         ), 'none') as actual,
         case when bool_and(exists (
           select 1 from information_schema.columns c
           where c.table_schema = required_columns.schema_name
             and c.table_name = required_columns.table_name
             and c.column_name = required_columns.column_name
         )) then 'READY' else 'BLOCKED' end as status,
         coalesce(string_agg(column_name, ', ' order by column_name) filter (
           where not exists (select 1 from information_schema.columns c
                             where c.table_schema = required_columns.schema_name
                               and c.table_name = required_columns.table_name
                               and c.column_name = required_columns.column_name)
         ), '') as notes
  from required_columns
  group by schema_name, table_name
),
required_indexes(schema_name, table_name, index_name, columns) as (
  values ('campaign','link_tokens','campaign_link_tokens_active_expiry_idx',array['status','expires_at']::text[]),
    ('public','tax_rules','tax_rules_active_idx',array['rule_type','effective_from','effective_to']::text[]),
    ('public','energy_prices','energy_prices_active_idx',array['energy_type','scenario_type','effective_from','effective_to']::text[]),
    ('public','internal_concern_priorities','internal_concern_priorities_order_idx',array['priority_rank','concern_type']::text[]),
    ('public','internal_vehicle_alias_mappings','internal_vehicle_alias_status_idx',array['mapping_status','normalized_model_name']::text[]),
    ('public','internal_vehicle_service_benchmarks','internal_benchmarks_vehicle_cohort_idx',array['vehicle_id','vehicle_age_bucket']::text[])
),
index_checks as (
  select 'INDEX ' || r.schema_name || '.' || r.index_name as component,
         'valid index on ' || array_to_string(r.columns, ', ') as expected,
         coalesce((select array_to_string(array_agg(a.attname::text order by k.ordinality), ', ')
                   from pg_index i join pg_class t on t.oid=i.indrelid
                   join pg_namespace n on n.oid=t.relnamespace join pg_class ix on ix.oid=i.indexrelid
                   cross join lateral unnest(i.indkey) with ordinality as k(attnum, ordinality)
                   join pg_attribute a on a.attrelid=t.oid and a.attnum=k.attnum
                   where n.nspname=r.schema_name and t.relname=r.table_name and ix.relname=r.index_name
                     and i.indisvalid and i.indisready and k.ordinality <= i.indnkeyatts), 'MISSING_OR_INVALID') as actual,
         case when exists (select 1 from pg_index i join pg_class t on t.oid=i.indrelid
                           join pg_namespace n on n.oid=t.relnamespace join pg_class ix on ix.oid=i.indexrelid
                           where n.nspname=r.schema_name and t.relname=r.table_name and ix.relname=r.index_name
                             and i.indisvalid and i.indisready
                             and (select array_agg(a.attname::text order by k.ordinality)
                                  from unnest(i.indkey) with ordinality as k(attnum, ordinality)
                                  join pg_attribute a on a.attrelid=t.oid and a.attnum=k.attnum
                                  where k.ordinality <= i.indnkeyatts)=r.columns)
              then 'READY' else 'BLOCKED' end as status,
         ''::text as notes
  from required_indexes r
),
required_unique(schema_name, table_name, columns) as (
  values ('campaign','link_tokens',array['id']::text[]),
    ('campaign','link_tokens',array['token_hash']::text[]),
    ('public','tax_rules',array['id']::text[]),
    ('public','tax_rules',array['rule_key']::text[]),
    ('public','energy_prices',array['id']::text[]),
    ('public','internal_research_sources',array['id']::text[]),
    ('public','internal_concern_priorities',array['id']::text[]),
    ('public','internal_concern_priorities',array['research_source_id','concern_type','snapshot_period']::text[]),
    ('public','internal_vehicle_alias_mappings',array['id']::text[]),
    ('public','internal_vehicle_alias_mappings',array['source_id','raw_model_name','snapshot_date']::text[]),
    ('public','internal_vehicle_service_benchmarks',array['id']::text[]),
    ('public','internal_vehicle_service_benchmarks',array['vehicle_id','vehicle_age_bucket','source_id','snapshot_date']::text[])
),
unique_checks as (
  select 'UNIQUE ' || schema_name || '.' || table_name as component,
         array_to_string(columns, ', ') as expected,
         case when exists (
           select 1 from pg_index i
           where i.indrelid=to_regclass(format('%I.%I', required_unique.schema_name, required_unique.table_name))
             and i.indisunique and i.indisvalid and i.indisready and i.indpred is null
             and (select array_agg(a.attname::text order by k.ordinality)
                  from unnest(i.indkey) with ordinality as k(attnum, ordinality)
                  join pg_attribute a on a.attrelid=i.indrelid and a.attnum=k.attnum
                  where k.ordinality <= i.indnkeyatts)=required_unique.columns
         ) then 'PRESENT' else 'MISSING' end as actual,
         case when exists (
           select 1 from pg_index i
           where i.indrelid=to_regclass(format('%I.%I', required_unique.schema_name, required_unique.table_name))
             and i.indisunique and i.indisvalid and i.indisready and i.indpred is null
             and (select array_agg(a.attname::text order by k.ordinality)
                  from unnest(i.indkey) with ordinality as k(attnum, ordinality)
                  join pg_attribute a on a.attrelid=i.indrelid and a.attnum=k.attnum
                  where k.ordinality <= i.indnkeyatts)=required_unique.columns
         ) then 'READY' else 'BLOCKED' end as status,
         ''::text as notes
  from required_unique
),
required_fks(schema_name, table_name, column_name, target_schema, target_table, target_column) as (
  values ('campaign','link_tokens','quiz_result_id','campaign','quiz_results','id'),
    ('public','internal_concern_priorities','research_source_id','public','internal_research_sources','id'),
    ('public','internal_vehicle_alias_mappings','source_id','public','internal_research_sources','id'),
    ('public','internal_vehicle_alias_mappings','vehicle_id','public','vehicle_profiles','id'),
    ('public','internal_vehicle_service_benchmarks','source_id','public','internal_research_sources','id'),
    ('public','internal_vehicle_service_benchmarks','vehicle_id','public','vehicle_profiles','id')
),
fk_checks as (
  select 'FOREIGN KEY ' || r.schema_name || '.' || r.table_name || '.' || r.column_name as component,
         r.target_schema || '.' || r.target_table || '(' || r.target_column || ')' as expected,
         case when exists (
           select 1 from pg_constraint c
           where c.contype='f' and c.convalidated
             and c.conrelid=to_regclass(format('%I.%I',r.schema_name,r.table_name))
             and c.confrelid=to_regclass(format('%I.%I',r.target_schema,r.target_table))
             and (select array_agg(a.attname::text order by k.ordinality) from unnest(c.conkey) with ordinality as k(attnum,ordinality) join pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.attnum)=array[r.column_name]::text[]
             and (select array_agg(a.attname::text order by k.ordinality) from unnest(c.confkey) with ordinality as k(attnum,ordinality) join pg_attribute a on a.attrelid=c.confrelid and a.attnum=k.attnum)=array[r.target_column]::text[]
         ) then 'PRESENT' else 'MISSING' end as actual,
         case when exists (
           select 1 from pg_constraint c
           where c.contype='f' and c.convalidated
             and c.conrelid=to_regclass(format('%I.%I',r.schema_name,r.table_name))
             and c.confrelid=to_regclass(format('%I.%I',r.target_schema,r.target_table))
             and (select array_agg(a.attname::text order by k.ordinality) from unnest(c.conkey) with ordinality as k(attnum,ordinality) join pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.attnum)=array[r.column_name]::text[]
             and (select array_agg(a.attname::text order by k.ordinality) from unnest(c.confkey) with ordinality as k(attnum,ordinality) join pg_attribute a on a.attrelid=c.confrelid and a.attnum=k.attnum)=array[r.target_column]::text[]
         ) then 'READY' else 'BLOCKED' end as status,
         ''::text as notes
  from required_fks r
),
restricted_tables(schema_name, table_name, service_write) as (
  values ('campaign','link_tokens',true), ('public','tax_rules',false),
    ('public','energy_prices',false), ('public','internal_research_sources',true),
    ('public','internal_concern_priorities',true), ('public','internal_vehicle_alias_mappings',true),
    ('public','internal_vehicle_service_benchmarks',true)
),
security_checks as (
  select 'SECURITY ' || r.schema_name || '.' || r.table_name as component,
         case when r.service_write then 'RLS; client roles denied; service_role CRUD' else 'RLS; client roles denied; service_role SELECT only' end as expected,
         case when c.relrowsecurity
              and not has_table_privilege('anon',c.oid,'SELECT')
              and not has_table_privilege('anon',c.oid,'INSERT')
              and not has_table_privilege('anon',c.oid,'UPDATE')
              and not has_table_privilege('anon',c.oid,'DELETE')
              and not has_table_privilege('authenticated',c.oid,'SELECT')
              and not has_table_privilege('authenticated',c.oid,'INSERT')
              and not has_table_privilege('authenticated',c.oid,'UPDATE')
              and not has_table_privilege('authenticated',c.oid,'DELETE')
              and has_table_privilege('service_role',c.oid,'SELECT')
              and (case when r.service_write then
                has_table_privilege('service_role',c.oid,'INSERT') and has_table_privilege('service_role',c.oid,'UPDATE') and has_table_privilege('service_role',c.oid,'DELETE')
                else not has_table_privilege('service_role',c.oid,'INSERT') and not has_table_privilege('service_role',c.oid,'UPDATE') and not has_table_privilege('service_role',c.oid,'DELETE') end)
              then 'PASS' else 'FAIL' end as actual,
         case when c.relrowsecurity
              and not has_table_privilege('anon',c.oid,'SELECT') and not has_table_privilege('anon',c.oid,'INSERT') and not has_table_privilege('anon',c.oid,'UPDATE') and not has_table_privilege('anon',c.oid,'DELETE')
              and not has_table_privilege('authenticated',c.oid,'SELECT') and not has_table_privilege('authenticated',c.oid,'INSERT') and not has_table_privilege('authenticated',c.oid,'UPDATE') and not has_table_privilege('authenticated',c.oid,'DELETE')
              and has_table_privilege('service_role',c.oid,'SELECT')
              and (case when r.service_write then has_table_privilege('service_role',c.oid,'INSERT') and has_table_privilege('service_role',c.oid,'UPDATE') and has_table_privilege('service_role',c.oid,'DELETE') else not has_table_privilege('service_role',c.oid,'INSERT') and not has_table_privilege('service_role',c.oid,'UPDATE') and not has_table_privilege('service_role',c.oid,'DELETE') end)
              then 'READY' else 'BLOCKED' end as status,
         ''::text as notes
  from restricted_tables r
  left join pg_class c on c.oid=to_regclass(format('%I.%I',r.schema_name,r.table_name))
),
rpc_checks as (
  select 'RPC public.consume_campaign_handoff'::text as component,
         'one argument named p_token_hash text; execute only for service_role'::text as expected,
         coalesce(pg_get_function_identity_arguments(p.oid), 'MISSING') as actual,
         case when p.oid is not null
               and pg_get_function_identity_arguments(p.oid)='p_token_hash text'
               and not has_function_privilege('anon',p.oid,'EXECUTE')
               and not has_function_privilege('authenticated',p.oid,'EXECUTE')
               and has_function_privilege('service_role',p.oid,'EXECUTE')
              then 'READY' else 'BLOCKED' end as status,
         ''::text as notes
  from (select to_regprocedure('public.consume_campaign_handoff(text)') as oid) f
  left join pg_proc p on p.oid=f.oid
  union all
  select 'RPC public.dev_schema_contract'::text as component,
         'no arguments; execute only for service_role'::text as expected,
         coalesce(pg_get_function_identity_arguments(p.oid), 'MISSING') as actual,
         case when p.oid is not null
               and pg_get_function_identity_arguments(p.oid)=''
               and not has_function_privilege('anon',p.oid,'EXECUTE')
               and not has_function_privilege('authenticated',p.oid,'EXECUTE')
               and has_function_privilege('service_role',p.oid,'EXECUTE')
              then 'READY' else 'BLOCKED' end as status,
         'Returns schema metadata only; no table rows.'::text as notes
  from (select to_regprocedure('public.dev_schema_contract()') as oid) f
  left join pg_proc p on p.oid=f.oid
),
state_checks as (
  select 'BOT STATE ' || s.table_name as component,
         'remains in public'::text as expected,
         coalesce(string_agg(n.nspname, ', ' order by n.nspname),'MISSING') as actual,
         case when bool_or(n.nspname='public') then 'READY' else 'BLOCKED' end as status,
         'This package does not move or alter this table.'::text as notes
  from (values ('conversation_contexts'),('conversation_flows'),('vehicle_preference_profiles'),('vehicle_comparison_sessions'),('cost_calculations'),('cost_scenarios'),('recent_user_results'),('group_member_bot_profiles')) s(table_name)
  left join pg_class c on c.relname=s.table_name and c.relkind in ('r','p')
  left join pg_namespace n on n.oid=c.relnamespace
  group by s.table_name
),
checks as (
  select * from table_checks union all
  select * from column_checks union all
  select * from index_checks union all
  select * from unique_checks union all
  select * from fk_checks union all
  select * from security_checks union all
  select * from rpc_checks union all
  select * from state_checks
)
select component, expected, actual, status, notes
from checks
union all
select 'OVERALL', 'all checks READY',
       case when bool_and(status='READY') then 'MVP_SCHEMA_READY' else 'BLOCKED' end,
       case when bool_and(status='READY') then 'MVP_SCHEMA_READY' else 'BLOCKED' end,
       'No migration or data write is performed by this verification query.'
from checks
order by component;
