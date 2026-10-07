-- Serverless-safe, privacy-preserving conversational state.  scope_hash is
-- already a SHA-256 hash of the LINE user/group scope, never a raw LINE ID.
create table if not exists bot_sessions (
  scope_hash text primary key,
  cost_flow jsonb,
  vehicle_need_context jsonb,
  expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);

create index if not exists bot_sessions_expires_at_idx on bot_sessions (expires_at);
alter table bot_sessions enable row level security;
