-- Reusable verified product features for contextual guidance.  These are not
-- copied into chat prompts so additional EV models can use the same mechanism.
create table if not exists vehicle_features (
  id uuid primary key default gen_random_uuid(),
  manufacturer text not null default 'TOYOTA',
  model_name text not null,
  feature_code text not null,
  description text not null,
  source_type text not null check (source_type in ('official', 'knowledge_base')),
  source_url text not null,
  verified_at timestamptz not null,
  valid_until timestamptz,
  created_at timestamptz not null default now(),
  unique (manufacturer, model_name, feature_code)
);

create index if not exists vehicle_features_lookup_idx
  on vehicle_features (manufacturer, model_name, feature_code);

alter table vehicle_features enable row level security;

insert into vehicle_features (
  manufacturer, model_name, feature_code, description, source_type, source_url, verified_at
) values (
  'TOYOTA', 'bZ4X', 'HOME_110V_CHARGING',
  'bZ4X 隨車附原廠 AC 充電線，可連接一般家用 110V 插座充電',
  'official', 'https://www.toyota.com.tw/bZ/bZ4X/charge.aspx', now()
) on conflict (manufacturer, model_name, feature_code) do update set
  description = excluded.description,
  source_type = excluded.source_type,
  source_url = excluded.source_url,
  verified_at = excluded.verified_at;
