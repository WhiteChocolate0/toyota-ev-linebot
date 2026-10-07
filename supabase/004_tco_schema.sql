-- TCO 資料層：既有 vehicle_profiles 保存官方車款資料；以下保存版本化規則與估算假設。
alter table vehicle_profiles
  add column if not exists engine_cc integer,
  add column if not exists motor_ps numeric,
  add column if not exists battery_capacity_kwh numeric,
  add column if not exists tire_spec text;

create table if not exists tax_rules (
  id uuid primary key default gen_random_uuid(),
  rule_type text not null,
  powertrain text,
  min_engine_cc integer,
  max_engine_cc integer,
  min_motor_ps numeric,
  max_motor_ps numeric,
  annual_amount numeric not null,
  exempt boolean not null default false,
  effective_from date not null,
  effective_to date,
  source_url text not null,
  source_level text not null default 'B' check (source_level in ('A', 'B', 'C', 'D')),
  verified_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists energy_prices (
  id uuid primary key default gen_random_uuid(),
  energy_type text not null check (energy_type in ('fuel_95', 'home_electricity', 'public_charging')),
  provider text,
  price_per_unit numeric not null,
  unit text not null,
  effective_from date,
  effective_to date,
  source_type text not null,
  source_url text,
  source_level text not null check (source_level in ('A', 'B', 'C', 'D')),
  verified_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists vehicle_cost_defaults (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid not null references vehicle_profiles(id) on delete cascade,
  annual_maintenance_default numeric,
  annual_insurance_default numeric,
  tire_set_price_default numeric,
  tire_lifespan_km integer,
  source_type text not null,
  source_url text,
  source_level text not null default 'C' check (source_level in ('A', 'B', 'C', 'D')),
  confidence_level text not null check (confidence_level in ('low', 'medium', 'high')),
  assumption_version text not null,
  verified_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists residual_value_scenarios (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid not null references vehicle_profiles(id) on delete cascade,
  ownership_years integer not null check (ownership_years between 1 and 15),
  scenario text not null check (scenario in ('conservative', 'base', 'optimistic')),
  residual_rate numeric not null check (residual_rate between 0 and 1),
  source_type text not null,
  source_url text,
  source_level text not null default 'C' check (source_level in ('A', 'B', 'C', 'D')),
  methodology text not null,
  assumption_version text not null,
  created_at timestamptz not null default now(),
  unique (vehicle_id, ownership_years, scenario, assumption_version)
);

create table if not exists calculator_assumption_versions (
  version text primary key,
  name text not null,
  effective_from date not null,
  effective_to date,
  description text,
  created_at timestamptz not null default now()
);

create table if not exists cost_calculations (
  id uuid primary key default gen_random_uuid(),
  user_id_hash text,
  group_id uuid references groups(id) on delete set null,
  vehicle_a_id uuid references vehicle_profiles(id),
  vehicle_b_id uuid references vehicle_profiles(id),
  annual_mileage integer not null,
  ownership_years integer not null check (ownership_years between 1 and 15),
  inputs_json jsonb not null,
  assumptions_json jsonb not null,
  result_json jsonb not null,
  assumption_version text not null references calculator_assumption_versions(version),
  created_at timestamptz not null default now()
);

create index if not exists tax_rules_effective_idx on tax_rules (effective_from, effective_to);
create index if not exists energy_prices_type_effective_idx on energy_prices (energy_type, effective_from, effective_to);
create index if not exists cost_calculations_user_created_idx on cost_calculations (user_id_hash, created_at desc);

alter table tax_rules enable row level security;
alter table energy_prices enable row level security;
alter table vehicle_cost_defaults enable row level security;
alter table residual_value_scenarios enable row level security;
alter table calculator_assumption_versions enable row level security;
alter table cost_calculations enable row level security;
