-- Scope and lifecycle hardening.  Existing group rows are retained and all
-- private rows receive a deterministic scope key; no conversation text is added.

alter table conversation_contexts add column if not exists scope_key text;
update conversation_contexts
set scope_key = case when group_id is null then 'private:' || user_id_hash
                     else 'group:' || group_id::text || ':user:' || user_id_hash end
where scope_key is null;
alter table conversation_contexts alter column scope_key set not null;
alter table conversation_contexts drop constraint if exists conversation_contexts_group_id_user_id_hash_key;
create unique index if not exists conversation_contexts_scope_key_key on conversation_contexts (scope_key);

alter table conversation_flows add column if not exists scope_key text;
update conversation_flows
set scope_key = case when group_id is null then 'private:' || owner_user_id_hash
                     else 'group:' || group_id::text || ':user:' || owner_user_id_hash end
where scope_key is null;
alter table conversation_flows alter column scope_key set not null;
alter table conversation_flows alter column current_state drop not null;
alter table conversation_flows drop constraint if exists conversation_flows_group_id_owner_user_id_hash_flow_type_key;
create unique index if not exists conversation_flows_scope_flow_key on conversation_flows (scope_key, flow_type);
create index if not exists conversation_flows_active_scope_idx on conversation_flows (scope_key, status, updated_at desc)
  where status in ('active', 'paused');
alter table conversation_flows drop constraint if exists conversation_flows_active_requires_state;
alter table conversation_flows add constraint conversation_flows_active_requires_state
  check (status <> 'active' or current_state is not null);

alter table vehicle_comparison_sessions add column if not exists scope_key text;
alter table vehicle_comparison_sessions add column if not exists source_type text not null default 'group'
  check (source_type in ('user', 'group'));
alter table vehicle_comparison_sessions add column if not exists status text not null default 'active'
  check (status in ('active', 'paused', 'completed', 'cancelled'));
alter table vehicle_comparison_sessions add column if not exists expires_at timestamptz;
update vehicle_comparison_sessions
set scope_key = case when group_id is null then 'private:' || owner_user_id_hash
                     else 'group:' || group_id::text || ':user:' || owner_user_id_hash end,
    source_type = case when group_id is null then 'user' else 'group' end,
    expires_at = coalesce(expires_at, updated_at + interval '30 days')
where scope_key is null or expires_at is null;
alter table vehicle_comparison_sessions alter column scope_key set not null;
alter table vehicle_comparison_sessions alter column expires_at set not null;
alter table vehicle_comparison_sessions drop constraint if exists vehicle_comparison_sessions_group_id_owner_user_id_hash_key;
create unique index if not exists vehicle_comparison_sessions_scope_key_key on vehicle_comparison_sessions (scope_key);
create index if not exists vehicle_comparison_sessions_active_scope_idx on vehicle_comparison_sessions (scope_key, status, updated_at desc)
  where status in ('active', 'paused');

-- Do not delete historical scenarios.  The check protects all new writes; an
-- existing legacy orphan remains visible for later manual remediation.
alter table cost_scenarios drop constraint if exists cost_scenarios_parent_required;
alter table cost_scenarios add constraint cost_scenarios_parent_required
  check (parent_calculation_id is not null) not valid;
create index if not exists cost_scenarios_parent_created_idx on cost_scenarios (parent_calculation_id, created_at desc);

-- PostgreSQL unique constraints allow several NULLs.  Give any old NULL row a
-- stable identifier first, then require an ID for future completed results.
update recent_user_results set result_id = id::text where result_id is null;
alter table recent_user_results alter column result_id set not null;

-- Versioned, source-backed specifications that do not belong in the mutable
-- comparison-session payload.  vehicle_profiles remains the catalogue identity.
create table if not exists vehicle_specifications (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid not null references vehicle_profiles(id) on delete cascade,
  official_range_km numeric check (official_range_km > 0),
  charging_requirement text,
  warranty_json jsonb not null default '{}'::jsonb,
  source_url text not null,
  verified_at timestamptz not null,
  valid_until timestamptz,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (vehicle_id, verified_at)
);
create index if not exists vehicle_specifications_active_vehicle_idx
  on vehicle_specifications (vehicle_id, verified_at desc) where is_active;
alter table vehicle_specifications enable row level security;

-- Canonical JSON accessors remove ambiguity between the legacy and conversational
-- cost payload names while keeping historic columns backward compatible.
create or replace view cost_calculation_canonical as
select calculation_id, vehicle_a_id, vehicle_b_id,
       coalesce(monthly_mileage * 12, annual_mileage) as annual_mileage,
       ownership_years,
       coalesce(assumptions, assumptions_json, '{}'::jsonb) as assumptions_json,
       coalesce(current_result, result_json, '{}'::jsonb) as result_json,
       created_at, updated_at
from cost_calculations;
