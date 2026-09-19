create table silver.owner (
  hs_owner_id text primary key, email text, first_name text, last_name text,
  is_active boolean not null default true, updated_at timestamptz not null default now()
);
create table silver.pipeline (hs_pipeline_id text primary key, label text not null);
create table silver.stage (
  hs_pipeline_id text not null references silver.pipeline, hs_stage_id text not null,
  label text not null, display_order int not null,
  is_closed boolean not null, probability numeric(4,3),
  is_won  boolean generated always as (is_closed and probability = 1.0) stored,
  is_lost boolean generated always as (is_closed and probability = 0.0) stored,
  primary key (hs_pipeline_id, hs_stage_id)
);
create table silver.deal (
  hs_deal_id text primary key, name text, amount numeric(18,2), currency text,
  hs_pipeline_id text not null, hs_stage_id text not null, hs_owner_id text,
  created_at timestamptz, close_date timestamptz, closed_at timestamptz,
  is_open boolean not null, is_won boolean not null default false, is_lost boolean not null default false,
  lost_reason_hs text, source text,
  last_activity_at timestamptz, next_activity_at timestamptz,
  num_contacts int not null default 0, close_date_pushes int not null default 0,
  hs_updated_at timestamptz not null, ingested_at timestamptz not null default now(),
  is_archived boolean not null default false
);
create index on silver.deal (hs_owner_id, is_open);
create index on silver.deal (closed_at);
create table silver.deal_stage_history (
  hs_deal_id text not null, hs_pipeline_id text not null, hs_stage_id text not null,
  entered_at timestamptz not null, exited_at timestamptz,
  primary key (hs_deal_id, hs_stage_id, entered_at)
);
create table silver.deal_property_change (
  hs_deal_id text not null, property text not null,
  old_value text, new_value text, changed_at timestamptz not null,
  primary key (hs_deal_id, property, changed_at)
);
create table silver.deal_snapshot (
  snapshot_date date not null, hs_deal_id text not null,
  hs_stage_id text, amount numeric(18,2), close_date timestamptz,
  hs_owner_id text, is_open boolean,
  primary key (snapshot_date, hs_deal_id)
);
create table silver.contact (hs_contact_id text primary key, email_hash text, job_title text, lifecycle_stage text, hs_owner_id text, hs_updated_at timestamptz);
create table silver.company (hs_company_id text primary key, name text, industry text, employee_band text, hs_updated_at timestamptz);
create table silver.deal_contact (hs_deal_id text not null, hs_contact_id text not null, is_primary boolean default false, primary key (hs_deal_id, hs_contact_id));
create table silver.deal_company (hs_deal_id text not null, hs_company_id text not null, primary key (hs_deal_id, hs_company_id));
create table silver.activity (
  hs_activity_id text primary key,
  activity_type text not null check (activity_type in ('call','meeting','email','note','task')),
  hs_deal_id text, hs_contact_id text, hs_owner_id text,
  occurred_at timestamptz, due_at timestamptz, is_completed boolean,
  duration_sec int, direction text, outcome text,
  summary text, transcript_path text, hs_updated_at timestamptz
);
create index on silver.activity (hs_deal_id, occurred_at);
create table silver.quota (
  hs_owner_id text not null, period_start date not null, period_end date not null,
  amount numeric(18,2) not null, source text not null,
  primary key (hs_owner_id, period_start, period_end)
);
