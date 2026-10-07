-- 常用、可驗證的外部參數快取；目前用於中油 95 無鉛牌價。
create table if not exists reference_parameters (
  id uuid primary key default gen_random_uuid(),
  parameter_key text not null,
  value_numeric numeric not null,
  effective_date date,
  source_url text not null,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (parameter_key, effective_date)
);

create index if not exists reference_parameters_key_fetched_idx
  on reference_parameters (parameter_key, fetched_at desc);

alter table reference_parameters enable row level security;
