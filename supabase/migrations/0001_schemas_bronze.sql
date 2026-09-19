create schema if not exists bronze;
create schema if not exists silver;
create schema if not exists gold;
create schema if not exists serving;
create schema if not exists app;

create table bronze.hubspot_raw (
  object_type text not null, object_id text not null,
  payload jsonb not null, hs_updated_at timestamptz,
  ingested_at timestamptz not null default now(),
  primary key (object_type, object_id)
);  -- purge rows with ingested_at < now() - interval '30 days'
create index on bronze.hubspot_raw (ingested_at);
