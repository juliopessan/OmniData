-- Resumable ingestion (FR-ING-3): completed windows are never re-fetched after a crash.
create table app.ingest_window (
  job text not null,                       -- e.g. 'backfill'
  object_type text not null,
  window_start timestamptz not null, window_end timestamptz not null,
  status text not null default 'pending' check (status in ('pending','done','failed')),
  row_count int, attempts int not null default 0, error text,
  updated_at timestamptz not null default now(),
  primary key (job, object_type, window_start, window_end)
);
-- Incremental high-water mark per object type (hs_lastmodifieddate).
create table app.ingest_cursor (
  object_type text primary key,
  high_watermark timestamptz not null,
  updated_at timestamptz not null default now()
);
