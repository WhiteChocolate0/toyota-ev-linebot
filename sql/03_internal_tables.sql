-- PURPOSE: Create exactly the four internal tables consumed by the importer
-- and LinebotRepository/internal insights service.
-- EXPECTED: Internal source metadata, concern priorities, explicit vehicle
-- alias mappings, and sample-gated aggregate service benchmarks. RLS and
-- backend-only permissions are applied in 05_rls_permissions.sql.
-- No raw CDP rows are included in these tables or this migration.

begin;

-- Importer source registry and parent for source_id foreign keys.
create table if not exists public.internal_research_sources (
  id text primary key,
  title text not null,
  source_kind text not null check (source_kind in ('INTERNAL_ORGANIZER_RESEARCH', 'INTERNAL_AGGREGATED_CDP')),
  snapshot_period text not null,
  visibility text not null default 'INTERNAL_ORGANIZER' check (visibility = 'INTERNAL_ORGANIZER'),
  created_at timestamptz not null default now()
);

-- Consumer: LinebotRepository.list_internal_concern_priorities().
create table if not exists public.internal_concern_priorities (
  id uuid primary key,
  concern_type text not null,
  priority_rank integer not null check (priority_rank > 0),
  weight numeric not null check (weight >= 0 and weight <= 1),
  research_source_id text not null references public.internal_research_sources(id),
  snapshot_period text not null,
  visibility text not null check (visibility = 'INTERNAL_ORGANIZER'),
  created_at timestamptz not null default now(),
  unique (research_source_id, concern_type, snapshot_period)
);
create index if not exists internal_concern_priorities_order_idx
  on public.internal_concern_priorities (priority_rank, concern_type);

-- Consumer: guarded organizer aggregate importer; mappings are explicit and
-- unresolved raw names remain UNMAPPED / UNMAPPED_AMBIGUOUS.
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

-- Consumer: LinebotRepository/internal_insights_service. A-only amounts are
-- explicitly typed and never represented as TWD.
create table if not exists public.internal_vehicle_service_benchmarks (
  id uuid primary key,
  vehicle_id uuid not null references public.vehicle_profiles(id) on delete restrict,
  vehicle_age_bucket text not null check (vehicle_age_bucket in ('0-12', '13-24', '25-36', '37-59', '60+')),
  sample_size integer not null check (sample_size >= 0),
  avg_service_visits numeric,
  median_service_visits numeric,
  avg_paid_service_visits numeric,
  median_paid_service_visits numeric,
  avg_scheduled_maintenance_visits numeric,
  median_scheduled_maintenance_visits numeric,
  avg_repair_visits numeric,
  median_repair_visits numeric,
  avg_service_amount_a_currency numeric,
  median_service_amount_a_currency numeric,
  avg_maintenance_amount_a_currency numeric,
  median_maintenance_amount_a_currency numeric,
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

-- Lock down immediately as well as in the dedicated permissions step, so
-- running this file alone never exposes internal tables to client roles.
alter table public.internal_research_sources enable row level security;
alter table public.internal_concern_priorities enable row level security;
alter table public.internal_vehicle_alias_mappings enable row level security;
alter table public.internal_vehicle_service_benchmarks enable row level security;
revoke all on table public.internal_research_sources from public, anon, authenticated;
revoke all on table public.internal_concern_priorities from public, anon, authenticated;
revoke all on table public.internal_vehicle_alias_mappings from public, anon, authenticated;
revoke all on table public.internal_vehicle_service_benchmarks from public, anon, authenticated;
grant select, insert, update, delete on table public.internal_research_sources to service_role;
grant select, insert, update, delete on table public.internal_concern_priorities to service_role;
grant select, insert, update, delete on table public.internal_vehicle_alias_mappings to service_role;
grant select, insert, update, delete on table public.internal_vehicle_service_benchmarks to service_role;

commit;
