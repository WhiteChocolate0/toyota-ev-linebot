-- Database cleanup after the 2026Q3 catalog cutover.
-- Safe to re-run.  It removes only abandoned schema and the 2026-09-20
-- unbounded catalog seed; persisted conversations, calculations, knowledge,
-- price cache, features, and webhook de-duplication records are retained.

-- This table was never read or written by the application and has no rows in
-- the deployed project.  Group-level summaries are intentionally out of MVP.
drop table if exists group_summaries;

-- These were a proposed rule/default layer from the early TCO design.  The
-- released full-TCO wizard collects transparent user assumptions at runtime,
-- and the repository has no dependency on these tables.
drop table if exists vehicle_cost_defaults;
drop table if exists residual_value_scenarios;
drop table if exists tax_rules;
drop table if exists energy_prices;
drop table if exists calculator_assumption_versions;

-- Remove the old seed, not user-entered or governed catalog rows.  All
-- affected entries are official rows seeded on 2026-09-20 without a catalog
-- version or expiry, including superseded bZ4X/CAMRY/YARIS CROSS entries.
delete from vehicle_profiles
where source_kind = 'official'
  and catalog_version is null
  and valid_until is null
  and verified_at = timestamptz '2026-09-20 19:54:03.250919+00';

-- Re-create the three current COROLLA CROSS gasoline selections as governed
-- 2026Q3 catalog rows.  They were previously updated in place from migration
-- 007 and therefore need explicit inserts after removing that legacy seed.
insert into vehicle_profiles (
  manufacturer, model_name, model_year, trim_name, drivetrain,
  purchase_price_ntd, energy_efficiency, energy_efficiency_unit,
  fuel_efficiency_km_per_l, aliases, source_url, verified_at, valid_until,
  source_kind, catalog_version, review_due_at, is_active
)
values
  ('TOYOTA', 'COROLLA CROSS', 2026, '豪華', 'ICE_GASOLINE',
   809000, 14.3, 'km_per_l', 14.3,
   '["corolla cross", "corolla cross gasoline"]'::jsonb,
   'https://www.toyota.com.tw/showroom/COROLLA_CROSS/',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08',
   'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'COROLLA CROSS', 2026, '豪華（選）', 'ICE_GASOLINE',
   839000, 14.3, 'km_per_l', 14.3,
   '["corolla cross", "corolla cross gasoline"]'::jsonb,
   'https://www.toyota.com.tw/showroom/COROLLA_CROSS/',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08',
   'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true),
  ('TOYOTA', 'COROLLA CROSS', 2026, 'The 60th', 'ICE_GASOLINE',
   889000, 14.2, 'km_per_l', 14.2,
   '["corolla cross", "corolla cross gasoline"]'::jsonb,
   'https://www.toyota.com.tw/showroom/COROLLA_CROSS/',
   timestamptz '2026-09-24 00:00:00+08', timestamptz '2026-12-31 23:59:59+08',
   'official', '2026Q3', timestamptz '2026-12-15 00:00:00+08', true)
on conflict (manufacturer, model_name, model_year, trim_name)
do update set
  drivetrain = excluded.drivetrain,
  purchase_price_ntd = excluded.purchase_price_ntd,
  energy_efficiency = excluded.energy_efficiency,
  energy_efficiency_unit = excluded.energy_efficiency_unit,
  fuel_efficiency_km_per_l = excluded.fuel_efficiency_km_per_l,
  aliases = excluded.aliases,
  source_url = excluded.source_url,
  verified_at = excluded.verified_at,
  valid_until = excluded.valid_until,
  source_kind = excluded.source_kind,
  catalog_version = excluded.catalog_version,
  review_due_at = excluded.review_due_at,
  is_active = excluded.is_active;

-- Replace the pre-fix quality view even when 013 was first executed before
-- its URL-regex correction.
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
