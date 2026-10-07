create table if not exists recent_user_results (
 id uuid primary key default gen_random_uuid(), user_id_hash text not null, result_type text not null,
 result_id text, summary_json jsonb not null default '{}', completed_at timestamptz not null default now(), expires_at timestamptz not null,
 unique (user_id_hash, result_type, result_id)
);
create index if not exists recent_user_results_user_completed_idx on recent_user_results (user_id_hash, completed_at desc);
alter table recent_user_results enable row level security;
