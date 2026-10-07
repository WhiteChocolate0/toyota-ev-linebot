-- Reconcile the conversational calculator record with the earlier TCO schema.
-- 004 may already have created cost_calculations, so 009 alone cannot add columns.
alter table cost_calculations add column if not exists calculation_id uuid;
-- A fresh 009 table has calculation_id but no legacy id.  A 004 table has id
-- but no calculation_id.  Handle both schemas without assuming either one.
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'cost_calculations' and column_name = 'id'
  ) then
    update cost_calculations set calculation_id = id where calculation_id is null;
  end if;
end $$;
alter table cost_calculations alter column calculation_id set default gen_random_uuid();
alter table cost_calculations alter column calculation_id set not null;
create unique index if not exists cost_calculations_calculation_id_key on cost_calculations (calculation_id);

alter table cost_calculations
  add column if not exists annual_mileage numeric,
  add column if not exists inputs_json jsonb,
  add column if not exists assumptions_json jsonb,
  add column if not exists result_json jsonb,
  add column if not exists assumption_version text,
  add column if not exists monthly_mileage numeric,
  add column if not exists fuel_price numeric,
  add column if not exists home_charge_ratio numeric,
  add column if not exists public_charge_ratio numeric,
  add column if not exists home_electricity_price numeric,
  add column if not exists public_electricity_price numeric,
  add column if not exists phev_electric_ratio numeric,
  add column if not exists assumptions jsonb not null default '{}'::jsonb,
  add column if not exists current_result jsonb,
  add column if not exists updated_at timestamptz not null default now();

-- Old rows retain their original TCO payload; conversational rows now use
-- both the legacy audit payload and the concise per-field columns above.
alter table cost_calculations alter column assumption_version drop not null;
