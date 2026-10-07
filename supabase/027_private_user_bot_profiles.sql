create table if not exists private_user_bot_profiles (
 user_id_hash text primary key, has_seen_welcome boolean not null default false, has_seen_private_menu boolean not null default false,
 first_interaction_at timestamptz, last_interaction_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table private_user_bot_profiles enable row level security;
