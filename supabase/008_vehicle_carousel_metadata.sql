alter table vehicle_profiles add column if not exists display_name text;
alter table vehicle_profiles add column if not exists display_order integer;
alter table vehicle_profiles add column if not exists is_active boolean not null default true;
alter table vehicle_profiles add column if not exists image_url text;

create index if not exists vehicle_profiles_display_order_idx on vehicle_profiles (display_order);
