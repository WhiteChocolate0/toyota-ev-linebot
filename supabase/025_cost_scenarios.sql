create table if not exists cost_scenarios (
 id uuid primary key default gen_random_uuid(), parent_calculation_id uuid references cost_calculations(calculation_id) on delete cascade,
 scenario_type text not null, override_json jsonb not null, result_json jsonb not null, created_at timestamptz not null default now()
);
