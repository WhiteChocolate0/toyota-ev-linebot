-- Short-lived structured continuation metadata. No raw LINE message text.
create table if not exists conversation_contexts (
  id uuid primary key default gen_random_uuid(), group_id uuid references groups(id) on delete cascade,
  user_id_hash text not null, context_json jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(), expires_at timestamptz not null,
  unique (group_id, user_id_hash)
);
create index if not exists conversation_contexts_expiry_idx on conversation_contexts (expires_at);
alter table conversation_contexts enable row level security;
