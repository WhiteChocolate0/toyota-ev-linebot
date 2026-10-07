-- Official vehicle catalog refresh, verified 2026-09-24 (Asia/Taipei).
-- Only values that appear together on a TOYOTA Taiwan official specification
-- page are added as auto-fill data.  Do not infer a trim's price or efficiency
-- from another trim or from a third-party listing.

alter table vehicle_profiles
  add column if not exists is_active boolean not null default true,
  add column if not exists source_kind text not null default 'official'
    check (source_kind in ('official', 'user_input', 'deprecated')),
  add column if not exists catalog_version text,
  add column if not exists review_due_at timestamptz;

-- Earlier installations may not have run migration 005.  Normalize their
-- legacy values before inserting this catalog, then enforce one vocabulary.
alter table vehicle_profiles drop constraint if exists vehicle_profiles_drivetrain_check;
update vehicle_profiles
set drivetrain = case drivetrain
  when 'gasoline' then 'ICE_GASOLINE'
  when 'diesel' then 'ICE_DIESEL'
  when 'hybrid' then 'HEV'
  when 'phev' then 'PHEV'
  when 'ev' then 'BEV'
  else drivetrain
end;
alter table vehicle_profiles
  add constraint vehicle_profiles_drivetrain_check
  check (drivetrain in ('ICE_GASOLINE', 'ICE_DIESEL', 'HEV', 'PHEV', 'BEV'));

create index if not exists vehicle_profiles_review_due_idx
  on vehicle_profiles (review_due_at)
  where is_active = true;

-- The catalog is reviewed quarterly.  `valid_until` is a hard runtime guard;
-- after it expires, the bot will ask the user for the missing value rather
-- than silently reusing a stale price or efficiency.
update vehicle_profiles
set is_active = false
where is_active = true
  and valid_until is not null
  and valid_until < timestamptz '2026-09-24 00:00:00+08';

-- Refresh the three previously seeded Corolla Cross gasoline trims.  The old
-- rows had no official price and no expiry date.
update vehicle_profiles
set purchase_price_ntd = case trim_name
      when '豪華' then 809000
      when '豪華（選）' then 839000
      when 'The 60th' then 889000
    end,
    source_url = 'https://www.toyota.com.tw/showroom/COROLLA_CROSS/',
    verified_at = timestamptz '2026-09-24 00:00:00+08',
    valid_until = timestamptz '2026-12-31 23:59:59+08',
    source_kind = 'official', catalog_version = '2026Q3',
    review_due_at = timestamptz '2026-12-15 00:00:00+08', is_active = true
where manufacturer = 'TOYOTA' and model_name = 'COROLLA CROSS'
  and drivetrain in ('ICE_GASOLINE', 'gasoline') and trim_name in ('豪華', '豪華（選）', 'The 60th');

-- `model_year` means the catalog data version here, not a claim about a VIN.
-- Rows use a fixed verification timestamp instead of now(), making the source
-- audit reproducible when this migration is replayed.
insert into vehicle_profiles (
  manufacturer, model_name, model_year, trim_name, drivetrain,
  purchase_price_ntd, energy_efficiency, energy_efficiency_unit,
  fuel_efficiency_km_per_l, electric_efficiency_km_per_kwh, aliases,
  source_url, verified_at, valid_until, source_kind, catalog_version,
  review_due_at, is_active
)
values
  ('TOYOTA', 'COROLLA CROSS', 2026, 'HYBRID 豪華', 'HEV',
   849000, 23.5, 'km_per_l', 23.5, null,
   '["corolla cross hybrid", "cc hybrid"]'::jsonb,
   'https://www.toyota.com.tw/showroom/COROLLA_CROSS/',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'YARiS CROSS', 2026, '享樂版', 'ICE_GASOLINE',
   695000, 17.5, 'km_per_l', 17.5, null,
   '["yaris cross", "yaris cross 享樂"]'::jsonb,
   'https://www.toyota.com.tw/showroom/YARISCROSS/',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'YARiS CROSS', 2026, '酷動版', 'ICE_GASOLINE',
   735000, 17.5, 'km_per_l', 17.5, null,
   '["yaris cross", "yaris cross 酷動"]'::jsonb,
   'https://www.toyota.com.tw/showroom/YARISCROSS/',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'YARiS CROSS', 2026, '潮玩版', 'ICE_GASOLINE',
   795000, 17.5, 'km_per_l', 17.5, null,
   '["yaris cross", "yaris cross 潮玩"]'::jsonb,
   'https://www.toyota.com.tw/showroom/YARISCROSS/',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'bZ4X', 2026, 'bZ4X', 'BEV',
   1280000, 6.7, 'km_per_kwh', null, 6.7,
   '["bz4x", "b z 4 x"]'::jsonb,
   'https://www.toyota.com.tw/showroom/bZ4X/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'URBAN CRUISER', 2026, 'Urban Cruiser', 'BEV',
   1270000, 6.8, 'km_per_kwh', null, 6.8,
   '["urban cruiser", "urbancruiser"]'::jsonb,
   'https://www.toyota.com.tw/showroom/URBAN_CRUISER/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'RAV4', 2026, '豪華', 'HEV',
   1040000, 24.0, 'km_per_l', 24.0, null,
   '["rav4", "rav 4"]'::jsonb,
   'https://www.toyota.com.tw/showroom/RAV4/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'RAV4', 2026, '尊爵', 'HEV',
   1170000, 24.0, 'km_per_l', 24.0, null,
   '["rav4", "rav 4"]'::jsonb,
   'https://www.toyota.com.tw/showroom/RAV4/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'RAV4', 2026, '尊爵+', 'HEV',
   1220000, 24.0, 'km_per_l', 24.0, null,
   '["rav4", "rav 4"]'::jsonb,
   'https://www.toyota.com.tw/showroom/RAV4/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'RAV4', 2026, '旗艦', 'HEV',
   1300000, 24.0, 'km_per_l', 24.0, null,
   '["rav4", "rav 4"]'::jsonb,
   'https://www.toyota.com.tw/showroom/RAV4/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'CAMRY', 2026, '旗艦', 'ICE_GASOLINE',
   1109000, 16.3, 'km_per_l', 16.3, null,
   '["camry"]'::jsonb,
   'https://www.toyota.com.tw/showroom/CAMRY/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'CAMRY', 2026, 'HYBRID 尊爵', 'HEV',
   1129000, 25.3, 'km_per_l', 25.3, null,
   '["camry hybrid", "camry 油電"]'::jsonb,
   'https://www.toyota.com.tw/showroom/CAMRY/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'CAMRY', 2026, 'HYBRID 旗艦', 'HEV',
   1250000, 25.3, 'km_per_l', 25.3, null,
   '["camry hybrid", "camry 油電"]'::jsonb,
   'https://www.toyota.com.tw/showroom/CAMRY/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'PRIUS PHEV', 2026, '旗艦', 'PHEV',
   1299000, 137.0, 'km_per_l', 137.0, 10.3,
   '["prius phev", "prius 插電式油電"]'::jsonb,
   'https://www.toyota.com.tw/showroom/PRIUS_PHEV/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'PRIUS PHEV', 2026, '鉑金', 'PHEV',
   1379000, 119.1, 'km_per_l', 119.1, 10.0,
   '["prius phev", "prius 插電式油電"]'::jsonb,
   'https://www.toyota.com.tw/showroom/PRIUS_PHEV/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'RAV4', 2026, 'PHEV 4WD', 'PHEV',
   1490000, 131.6, 'km_per_l', 131.6, 6.5,
   '["rav4 phev", "rav 4 phev"]'::jsonb,
   'https://www.toyota.com.tw/showroom/RAV4/fullsepc.aspx',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08', 'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true)
on conflict (manufacturer, model_name, model_year, trim_name)
do update set
  drivetrain = excluded.drivetrain,
  purchase_price_ntd = excluded.purchase_price_ntd,
  energy_efficiency = excluded.energy_efficiency,
  energy_efficiency_unit = excluded.energy_efficiency_unit,
  fuel_efficiency_km_per_l = excluded.fuel_efficiency_km_per_l,
  electric_efficiency_km_per_kwh = excluded.electric_efficiency_km_per_kwh,
  aliases = excluded.aliases, source_url = excluded.source_url,
  verified_at = excluded.verified_at, valid_until = excluded.valid_until,
  source_kind = excluded.source_kind, catalog_version = excluded.catalog_version,
  review_due_at = excluded.review_due_at, is_active = excluded.is_active;

-- Run this query as part of every catalog acceptance check.  It must return
-- zero rows before the catalog is promoted: each active auto-fill row needs an
-- official source, bounded freshness, a review date, a price, and the
-- efficiency fields required by its powertrain.
create or replace view vehicle_profile_quality_issues as
select id, model_name, model_year, trim_name, drivetrain,
  case
    when source_kind <> 'official' then 'non_official_source'
    when source_url !~ '^https://www\.toyota\.com\.tw/' then 'invalid_source_url'
    when valid_until is null or valid_until <= now() then 'expired_or_unbounded'
    when review_due_at is null then 'missing_review_date'
    when purchase_price_ntd is null or purchase_price_ntd <= 0 then 'missing_price'
    when drivetrain in ('ICE_GASOLINE', 'ICE_DIESEL', 'HEV') and fuel_efficiency_km_per_l is null then 'missing_fuel_efficiency'
    when drivetrain = 'BEV' and electric_efficiency_km_per_kwh is null then 'missing_electric_efficiency'
    when drivetrain = 'PHEV' and (fuel_efficiency_km_per_l is null or electric_efficiency_km_per_kwh is null) then 'missing_phev_efficiency'
    else null
  end as issue
from vehicle_profiles
where is_active = true;
