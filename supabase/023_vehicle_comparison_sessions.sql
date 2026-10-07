create table if not exists vehicle_comparison_sessions (
 id uuid primary key default gen_random_uuid(), group_id uuid references groups(id) on delete cascade,
 owner_user_id_hash text not null, vehicle_ids jsonb not null, comparison_dimensions jsonb not null default '[]', created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(group_id, owner_user_id_hash), check (jsonb_array_length(vehicle_ids) between 2 and 3)
);
alter table vehicle_comparison_sessions enable row level security;
