-- Per-member onboarding in a group. LINE user IDs remain hashed server-side.
create table if not exists group_member_bot_profiles (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references groups(id) on delete cascade,
  user_id_hash text not null,
  has_seen_onboarding boolean not null default false,
  first_interaction_at timestamptz not null default now(),
  last_interaction_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (group_id, user_id_hash)
);

create index if not exists group_member_bot_profiles_group_idx on group_member_bot_profiles (group_id, last_interaction_at desc);
alter table group_member_bot_profiles enable row level security;
