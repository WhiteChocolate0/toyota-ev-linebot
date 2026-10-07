-- PURPOSE: Create the minimum shared reference tables in public schema.
-- EXPECTED: public.tax_rules and public.energy_prices plus active lookup
-- indexes. effective_to is retained because SharedReferenceRepository filters
-- on that exact column. Existing tables/rows are not altered.

begin;

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
revoke all on table public.tax_rules from public, anon, authenticated;
grant select, insert, update, delete on table public.tax_rules to service_role;

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
revoke all on table public.energy_prices from public, anon, authenticated;
grant select, insert, update, delete on table public.energy_prices to service_role;

commit;
