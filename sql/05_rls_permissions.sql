-- PURPOSE: Reassert backend-only database boundaries after the table/RPC
-- scripts. This does not change table definitions or any user-state data.
-- EXPECTED: Internal tables are RLS-enabled and client roles cannot access
-- them; service_role can read/write internal tables. Shared reference tables
-- are RLS-enabled and service_role can read them (writes remain migration/admin
-- only). Token/RPC access is service-role-only.

begin;

alter table campaign.link_tokens enable row level security;
revoke all on table campaign.link_tokens from public, anon, authenticated;
grant select, insert, update, delete on table campaign.link_tokens to service_role;

alter table public.tax_rules enable row level security;
alter table public.energy_prices enable row level security;
revoke all on table public.tax_rules from public, anon, authenticated;
revoke all on table public.energy_prices from public, anon, authenticated;
revoke insert, update, delete on table public.tax_rules from service_role;
revoke insert, update, delete on table public.energy_prices from service_role;
grant select on table public.tax_rules to service_role;
grant select on table public.energy_prices to service_role;

alter table public.internal_research_sources enable row level security;
alter table public.internal_concern_priorities enable row level security;
alter table public.internal_vehicle_alias_mappings enable row level security;
alter table public.internal_vehicle_service_benchmarks enable row level security;
revoke all on table public.internal_research_sources from public, anon, authenticated;
revoke all on table public.internal_concern_priorities from public, anon, authenticated;
revoke all on table public.internal_vehicle_alias_mappings from public, anon, authenticated;
revoke all on table public.internal_vehicle_service_benchmarks from public, anon, authenticated;
grant select, insert, update, delete on table public.internal_research_sources to service_role;
grant select, insert, update, delete on table public.internal_concern_priorities to service_role;
grant select, insert, update, delete on table public.internal_vehicle_alias_mappings to service_role;
grant select, insert, update, delete on table public.internal_vehicle_service_benchmarks to service_role;

revoke all on function public.consume_campaign_handoff(text) from public, anon, authenticated;
grant execute on function public.consume_campaign_handoff(text) to service_role;
revoke all on function public.dev_schema_contract() from public, anon, authenticated;
grant execute on function public.dev_schema_contract() to service_role;

commit;
