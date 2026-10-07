-- User-owned multi-step wizards in a shared LINE group.
create table if not exists conversation_flows (
  id uuid primary key default gen_random_uuid(),
  group_id uuid references groups(id) on delete cascade,
  owner_user_id_hash text not null,
  flow_type text not null,
  current_state text not null,
  pending_field text,
  status text not null default 'active' check (status in ('active', 'paused', 'completed', 'cancelled')),
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (group_id, owner_user_id_hash, flow_type)
);

alter table conversation_flows enable row level security;
