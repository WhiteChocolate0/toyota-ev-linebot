create table if not exists group_concern_board (
 group_id uuid references groups(id) on delete cascade, concern_type text not null,
 status text not null check (status in ('OPEN','NEEDS_VERIFICATION','CLARIFIED','DISAGREEMENT')),
 evidence_count integer not null default 0, last_updated timestamptz not null default now(), expires_at timestamptz not null,
 primary key (group_id, concern_type)
);
create index if not exists group_concern_board_expiry_idx on group_concern_board (expires_at);
alter table group_concern_board enable row level security;
