-- Separate official fuel and electric efficiencies so PHEV can use both values.
alter table vehicle_profiles
  add column if not exists fuel_efficiency_km_per_l numeric check (fuel_efficiency_km_per_l > 0),
  add column if not exists electric_efficiency_km_per_kwh numeric check (electric_efficiency_km_per_kwh > 0);

comment on column vehicle_profiles.fuel_efficiency_km_per_l is 'Official published combined fuel efficiency, km/L';
comment on column vehicle_profiles.electric_efficiency_km_per_kwh is 'Official published electricity efficiency, km/kWh';
