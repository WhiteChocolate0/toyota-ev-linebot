-- Sprint 05: metadata-only group memory. Never persist LINE message bodies.
-- Behaviour labels receive a 100-day expiry in the application layer.
alter table groups add column if not exists last_summary_offer_at timestamptz;
alter table groups add column if not exists summary_opt_out_until timestamptz;

create table if not exists group_summaries (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references groups(id) on delete cascade,
  summary_json jsonb not null,
  created_at timestamptz not null default now(),
  deleted_at timestamptz
);
-- A previous schema version created this table without soft deletion.
-- `create table if not exists` does not alter it, so add the column explicitly.
alter table group_summaries add column if not exists deleted_at timestamptz;

create table if not exists group_member_signals (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references groups(id) on delete cascade,
  member_id_hash text not null,
  label text not null check (label in ('cost_focused','safety_focused','skeptical','ev_positive','neutral','decision_maker_candidate')),
  weight numeric(4,2) not null default 1,
  expires_at timestamptz not null,
  updated_at timestamptz not null default now(),
  unique (group_id, member_id_hash, label)
);

create index if not exists group_summaries_current_idx on group_summaries (group_id, created_at desc) where deleted_at is null;
create index if not exists group_member_signals_expiry_idx on group_member_signals (expires_at);
alter table group_summaries enable row level security;
alter table group_member_signals enable row level security;
