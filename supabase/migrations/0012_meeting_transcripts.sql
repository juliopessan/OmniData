-- Source of truth and permission boundary for meeting transcripts (ADR 0009). Chroma holds only the embedding + this row's
-- id and hs_owner_id as a coarse pre-filter; every result is re-checked against this table via Principal.owner_clause()
-- before it can be shown, so a bug or a stale index in Chroma can never leak another rep's transcript.
create table app.meeting_transcript (
  id uuid primary key default gen_random_uuid(),
  hs_deal_id text not null, hs_owner_id text not null, deal_name text not null,
  occurred_at timestamptz not null, text text not null,
  synthetic boolean not null default true, created_at timestamptz not null default now()
);
create index on app.meeting_transcript (hs_owner_id);
alter table app.meeting_transcript enable row level security;

-- repo.py reads serving.* only (its own contract); this view is the read side of app.meeting_transcript.
create view serving.v_meeting_transcript as
  select id, hs_deal_id, hs_owner_id, deal_name, occurred_at, text from app.meeting_transcript;
