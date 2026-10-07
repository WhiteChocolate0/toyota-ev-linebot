-- DEV ONLY. Do not run this file against Production without the explicitly
-- approved Production migration phase. It does not move or rename any existing
-- LINE Bot state table.
begin;

create extension if not exists pgcrypto;
create schema if not exists campaign;

create table if not exists campaign.link_tokens (
  id uuid primary key default gen_random_uuid(),
  quiz_result_id uuid not null references campaign.quiz_results(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  status text not null default 'active' check (status in ('active', 'consumed', 'expired', 'revoked')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  check ((status = 'consumed') = (consumed_at is not null))
);
create index if not exists campaign_link_tokens_active_expiry_idx
  on campaign.link_tokens (status, expires_at);
alter table campaign.link_tokens enable row level security;
revoke all on table campaign.link_tokens from anon, authenticated;
grant select, insert, update, delete on table campaign.link_tokens to service_role;

create table if not exists public.tax_rules (
  id uuid primary key default gen_random_uuid(),
  rule_key text not null unique,
  rule_type text not null,
  vehicle_scope text,
  value_json jsonb not null,
  effective_from date not null,
  effective_to date,
  source_id text,
  source_url text,
  source_type text not null default 'official',
  verified_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);
create index if not exists tax_rules_active_idx
  on public.tax_rules (rule_type, effective_from desc, effective_to);
alter table public.tax_rules enable row level security;
revoke all on table public.tax_rules from anon, authenticated;
revoke insert, update, delete on table public.tax_rules from service_role;
grant select on table public.tax_rules to service_role;

create table if not exists public.energy_prices (
  id uuid primary key default gen_random_uuid(),
  energy_type text not null,
  scenario_type text not null,
  price_value numeric not null check (price_value >= 0),
  price_unit text not null,
  effective_from date not null,
  effective_to date,
  source_id text,
  source_url text,
  source_type text not null default 'official',
  verified_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);
create index if not exists energy_prices_active_idx
  on public.energy_prices (energy_type, scenario_type, effective_from desc, effective_to);
alter table public.energy_prices enable row level security;
revoke all on table public.energy_prices from anon, authenticated;
revoke insert, update, delete on table public.energy_prices from service_role;
grant select on table public.energy_prices to service_role;

create table if not exists public.internal_research_sources (
  id text primary key,
  title text not null,
  source_kind text not null check (source_kind in ('INTERNAL_ORGANIZER_RESEARCH', 'INTERNAL_AGGREGATED_CDP')),
  snapshot_period text not null,
  visibility text not null default 'INTERNAL_ORGANIZER' check (visibility = 'INTERNAL_ORGANIZER'),
  created_at timestamptz not null default now()
);
create table if not exists public.internal_concern_priorities (
  id uuid primary key,
  concern_type text not null,
  priority_rank integer not null check (priority_rank > 0),
  weight numeric not null check (weight >= 0 and weight <= 1),
  research_source_id text not null references public.internal_research_sources(id),
  snapshot_period text not null,
  visibility text not null check (visibility = 'INTERNAL_ORGANIZER'),
  created_at timestamptz not null,
  unique (research_source_id, concern_type, snapshot_period)
);
create index if not exists internal_concern_priorities_order_idx
  on public.internal_concern_priorities (priority_rank, concern_type);
create table if not exists public.internal_vehicle_alias_mappings (
  id uuid primary key,
  raw_model_name text not null,
  normalized_model_name text not null,
  vehicle_id uuid references public.vehicle_profiles(id) on delete restrict,
  mapping_status text not null check (mapping_status in ('MAPPED', 'UNMAPPED', 'UNMAPPED_AMBIGUOUS')),
  source_id text not null references public.internal_research_sources(id),
  snapshot_date date not null,
  sample_size integer not null check (sample_size >= 0),
  visibility text not null check (visibility = 'INTERNAL_ORGANIZER'),
  check ((mapping_status = 'MAPPED') = (vehicle_id is not null)),
  unique (source_id, raw_model_name, snapshot_date)
);
create index if not exists internal_vehicle_alias_status_idx
  on public.internal_vehicle_alias_mappings (mapping_status, normalized_model_name);
create table if not exists public.internal_vehicle_service_benchmarks (
  id uuid primary key,
  vehicle_id uuid not null references public.vehicle_profiles(id) on delete restrict,
  vehicle_age_bucket text not null check (vehicle_age_bucket in ('0-12', '13-24', '25-36', '37-59', '60+')),
  sample_size integer not null check (sample_size >= 0),
  avg_service_visits numeric, median_service_visits numeric,
  avg_paid_service_visits numeric, median_paid_service_visits numeric,
  avg_scheduled_maintenance_visits numeric, median_scheduled_maintenance_visits numeric,
  avg_repair_visits numeric, median_repair_visits numeric,
  avg_service_amount_a_currency numeric, median_service_amount_a_currency numeric,
  avg_maintenance_amount_a_currency numeric, median_maintenance_amount_a_currency numeric,
  currency_type text not null check (currency_type = 'ANONYMIZED_A_CURRENCY'),
  source_id text not null references public.internal_research_sources(id),
  snapshot_date date not null,
  visibility text not null check (visibility = 'INTERNAL_ORGANIZER'),
  status text not null check (status in ('READY', 'INSUFFICIENT_SAMPLE')),
  check ((status = 'READY' and sample_size >= 30) or (status = 'INSUFFICIENT_SAMPLE' and sample_size < 30)),
  unique (vehicle_id, vehicle_age_bucket, source_id, snapshot_date)
);
create index if not exists internal_benchmarks_vehicle_cohort_idx
  on public.internal_vehicle_service_benchmarks (vehicle_id, vehicle_age_bucket);
alter table public.internal_research_sources enable row level security;
alter table public.internal_concern_priorities enable row level security;
alter table public.internal_vehicle_alias_mappings enable row level security;
alter table public.internal_vehicle_service_benchmarks enable row level security;
revoke all on table public.internal_research_sources from anon, authenticated;
revoke all on table public.internal_concern_priorities from anon, authenticated;
revoke all on table public.internal_vehicle_alias_mappings from anon, authenticated;
revoke all on table public.internal_vehicle_service_benchmarks from anon, authenticated;
grant select, insert, update, delete on table public.internal_research_sources to service_role;
grant select, insert, update, delete on table public.internal_concern_priorities to service_role;
grant select, insert, update, delete on table public.internal_vehicle_alias_mappings to service_role;
grant select, insert, update, delete on table public.internal_vehicle_service_benchmarks to service_role;

commit;
