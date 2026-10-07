create table if not exists cost_calculations (
  calculation_id uuid primary key default gen_random_uuid(),
  vehicle_a_id uuid references vehicle_profiles(id),
  vehicle_b_id uuid references vehicle_profiles(id),
  monthly_mileage numeric,
  ownership_years integer,
  fuel_price numeric,
  home_charge_ratio numeric,
  public_charge_ratio numeric,
  home_electricity_price numeric,
  public_electricity_price numeric,
  phev_electric_ratio numeric,
  assumptions jsonb not null default '{}'::jsonb,
  current_result jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
