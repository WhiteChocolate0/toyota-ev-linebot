-- TOYOTA EV 家庭小幫手：MVP 資料最小化 schema
-- 請於 Supabase SQL Editor 執行；後端僅使用 service-role key 存取。

create extension if not exists pgcrypto;

create table if not exists groups (
  id uuid primary key default gen_random_uuid(),
  line_group_id_hash text not null unique,
  status text not null default 'active' check (status in ('active', 'inactive', 'deleted')),
  discussion_stage text not null default 'onboarding',
  created_at timestamptz not null default now(),
  last_active_at timestamptz not null default now()
);

create table if not exists webhook_events (
  event_id text primary key,
  received_at timestamptz not null default now()
);

create table if not exists conversation_events (
  id uuid primary key default gen_random_uuid(),
  group_id uuid references groups(id) on delete cascade,
  message_type text not null,
  intent text,
  concern_type text,
  relevance_score numeric(4,3),
  summary text,
  created_at timestamptz not null default now()
);

create table if not exists concerns (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references groups(id) on delete cascade,
  concern_type text not null,
  severity text not null default 'normal',
  status text not null default 'open' check (status in ('open', 'resolved')),
  first_seen timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  unique (group_id, concern_type)
);

create table if not exists knowledge_sources (
  id text primary key,
  publisher text not null,
  title text not null,
  url text not null,
  category text not null,
  content text not null,
  verified_at timestamptz not null,
  valid_until timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists group_summaries (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references groups(id) on delete cascade,
  summary_json jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists conversation_events_group_created_idx
  on conversation_events (group_id, created_at desc);
create index if not exists concerns_group_status_idx
  on concerns (group_id, status);
create index if not exists knowledge_sources_category_valid_idx
  on knowledge_sources (category, valid_until);

-- No client-side policy is created: browser clients have no table access.
-- The server uses Supabase service-role credentials, which bypass RLS.
alter table groups enable row level security;
alter table webhook_events enable row level security;
alter table conversation_events enable row level security;
alter table concerns enable row level security;
alter table knowledge_sources enable row level security;
alter table group_summaries enable row level security;
