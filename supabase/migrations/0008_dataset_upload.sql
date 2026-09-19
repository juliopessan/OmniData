-- Audit trail of dataset uploads (file content is NOT stored: only its hash and stats, to keep the DB small and PII contained).
create table app.dataset_upload (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('deals','quotas')),
  filename text not null, sha256 text not null, size_bytes int not null,
  status text not null check (status in ('validated','imported','failed','rejected')),
  total_rows int not null default 0, imported_rows int not null default 0, error_count int not null default 0,
  options jsonb not null default '{}', errors jsonb not null default '[]', summary jsonb not null default '{}',
  uploaded_by text, created_at timestamptz not null default now(), imported_at timestamptz,
  org_id uuid not null default '00000000-0000-0000-0000-000000000001'
);
create index on app.dataset_upload (created_at desc);
create index on app.dataset_upload (kind, sha256);
alter table app.dataset_upload enable row level security;
