create table app.app_user (
  id uuid primary key default gen_random_uuid(),
  hs_owner_id text not null unique, phone_e164 text not null unique,
  display_name text, role text not null check (role in ('rep','manager','admin')),
  manager_user_id uuid references app.app_user,
  timezone text not null default 'America/Sao_Paulo',
  brief_time time not null default '07:30',
  status text not null default 'invited' check (status in ('invited','active','paused','revoked')),
  consent_text_version text, opted_in_at timestamptz, created_at timestamptz not null default now()
);
create table app.wa_message (
  id uuid primary key default gen_random_uuid(),
  wa_message_id text unique, user_id uuid references app.app_user,
  direction text not null check (direction in ('in','out')), kind text not null,
  payload jsonb not null,
  status text not null default 'received' check (status in ('received','processing','done','failed','ignored')),
  attempts int not null default 0, error text,
  received_at timestamptz not null default now(), processed_at timestamptz
);
create index on app.wa_message (status, received_at) where direction = 'in';
create table app.conversation_state (
  user_id uuid primary key references app.app_user,
  state text not null default 'idle', context jsonb not null default '{}',
  updated_at timestamptz not null default now(), expires_at timestamptz
);
create table app.pending_action (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app.app_user,
  kind text not null, params jsonb not null,
  risk text not null default 'normal' check (risk in ('normal','high')),
  status text not null default 'proposed'
    check (status in ('proposed','confirmed','executed','cancelled','expired','failed','undone')),
  idempotency_key text not null unique,
  before_state jsonb, after_state jsonb, hs_response jsonb,
  created_at timestamptz not null default now(), expires_at timestamptz,
  executed_at timestamptz, undo_deadline timestamptz
);
create table app.alert_event (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app.app_user,
  rule_key text not null, dedupe_key text not null, hs_deal_id text,
  attention_score numeric, sent_at timestamptz, viewed_at timestamptz,
  acted_at timestamptz, snoozed_until timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, dedupe_key)
);
create table app.loss_reason (
  id uuid primary key default gen_random_uuid(),
  hs_deal_id text not null, user_id uuid references app.app_user,
  reason_code text not null, free_text text, source text check (source in ('button','audio','text')),
  captured_at timestamptz not null default now()
);
create table app.llm_call (
  id uuid primary key default gen_random_uuid(), user_id uuid,
  purpose text not null, provider text not null, model text not null,
  input_tokens int, output_tokens int, cost_usd numeric(10,6), latency_ms int,
  created_at timestamptz not null default now()
);
create table app.audit_log (
  id bigserial primary key, user_id uuid, event text not null,
  detail jsonb not null default '{}', created_at timestamptz not null default now()
);
create table app.model_run (
  id uuid primary key default gen_random_uuid(), pipeline_id text, kind text not null,
  metrics jsonb not null, artifact_path text, trained_at timestamptz not null default now(),
  is_active boolean not null default false
);
