-- Hybrid RAG metadata and privacy-preserving knowledge-gap telemetry.
alter table knowledge_sources add column if not exists topic text;
alter table knowledge_sources add column if not exists source_type text not null default 'official_manufacturer';
alter table knowledge_sources add column if not exists vehicle_scope text;
alter table knowledge_sources add column if not exists country_scope text default 'TW';
alter table knowledge_sources add column if not exists keywords text[] not null default '{}';
alter table knowledge_sources add column if not exists is_active boolean not null default true;
alter table knowledge_sources add column if not exists priority integer not null default 0;
create index if not exists knowledge_sources_active_topic_idx on knowledge_sources (is_active, topic, valid_until);
create table if not exists knowledge_gap_logs (
  id uuid primary key default gen_random_uuid(), query_hash text not null, topic text,
  retrieval_score numeric, created_at timestamptz not null default now()
);
alter table knowledge_gap_logs enable row level security;
