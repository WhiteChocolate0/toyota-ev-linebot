-- Vehicle-selection metadata.  Populate only fields published together with
-- a verifiable official source; null means unknown, never an inferred value.
alter table vehicle_profiles
  add column if not exists length_mm integer check (length_mm > 0),
  add column if not exists width_mm integer check (width_mm > 0),
  add column if not exists height_mm integer check (height_mm > 0),
  add column if not exists wheelbase_mm integer check (wheelbase_mm > 0),
  add column if not exists seats integer check (seats between 1 and 12),
  add column if not exists cargo_capacity_l integer check (cargo_capacity_l > 0),
  add column if not exists cargo_notes text,
  add column if not exists rear_seat_foldable boolean,
  add column if not exists body_type text;

comment on column vehicle_profiles.cargo_capacity_l is 'Official published cargo capacity in litres; null means not published or not verified.';
comment on column vehicle_profiles.cargo_notes is 'Official, source-verifiable cargo / rear-seat notes only; no inferred capacity.';

create index if not exists vehicle_profiles_body_type_idx
  on vehicle_profiles (body_type) where is_active = true;
