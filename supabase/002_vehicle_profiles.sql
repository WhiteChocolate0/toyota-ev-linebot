-- 可版本化的 TOYOTA 車款資料；所有數字須附官方來源與驗證日期。
create table if not exists vehicle_profiles (
  id uuid primary key default gen_random_uuid(),
  manufacturer text not null default 'TOYOTA',
  model_name text not null,
  model_year integer,
  trim_name text,
  drivetrain text not null check (drivetrain in ('gasoline', 'hybrid', 'phev', 'ev', 'diesel')),
  purchase_price_ntd numeric,
  energy_efficiency numeric,
  energy_efficiency_unit text check (energy_efficiency_unit in ('km_per_l', 'km_per_kwh')),
  aliases jsonb not null default '[]'::jsonb,
  source_url text not null,
  verified_at timestamptz not null,
  valid_until timestamptz,
  created_at timestamptz not null default now(),
  unique (manufacturer, model_name, model_year, trim_name)
);

create index if not exists vehicle_profiles_model_name_idx
  on vehicle_profiles (manufacturer, model_name);

alter table vehicle_profiles enable row level security;
