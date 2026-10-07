-- Structured, nullable preferences; no raw family chat is stored.
create table if not exists vehicle_preference_profiles (
  id uuid primary key default gen_random_uuid(), group_id uuid references groups(id) on delete cascade,
  user_id_hash text not null, profile_json jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(), created_at timestamptz not null default now(),
  unique (group_id, user_id_hash)
);
alter table vehicle_preference_profiles enable row level security;
