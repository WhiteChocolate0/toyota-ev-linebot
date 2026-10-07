-- Toyota Taiwan official COROLLA CROSS gasoline efficiency profiles.
-- Source verified 2026-09-21; values are official combined average fuel efficiency.
insert into vehicle_profiles (
  manufacturer, model_name, trim_name, drivetrain,
  energy_efficiency, energy_efficiency_unit, fuel_efficiency_km_per_l,
  aliases, source_url, verified_at
)
select 'TOYOTA', 'COROLLA CROSS', values_to_insert.trim_name, 'ICE_GASOLINE',
       values_to_insert.efficiency, 'km_per_l', values_to_insert.efficiency,
       '["corolla cross", "corolla cross gasoline"]'::jsonb,
       'https://www.toyota.com.tw/showroom/COROLLA_CROSS/fullsepc.aspx', now()
from (values
  ('豪華', 14.3::numeric),
  ('豪華（選）', 14.3::numeric),
  ('The 60th', 14.2::numeric)
) as values_to_insert(trim_name, efficiency)
where not exists (
  select 1 from vehicle_profiles existing
  where existing.manufacturer = 'TOYOTA'
    and existing.model_name = 'COROLLA CROSS'
    and existing.trim_name = values_to_insert.trim_name
    and existing.drivetrain = 'ICE_GASOLINE'
);
