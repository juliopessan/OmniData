-- Agent harness telemetry (ADR 0003): which specialist ran which tool. Stores NO arguments, NO text.
create table app.agent_step (
  id bigserial primary key,
  run_id uuid not null, step_no int not null,
  user_id uuid, agent text not null, tool text not null,
  status text not null check (status in ('ok','empty','failed','rejected')),
  latency_ms int, created_at timestamptz not null default now(),
  org_id uuid not null default '00000000-0000-0000-0000-000000000001'
);
create index on app.agent_step (created_at, agent);
alter table app.agent_step enable row level security;

create view serving.v_agent_activity as
  select agent, date_trunc('day', created_at)::date as day, count(*) as steps,
         count(*) filter (where status = 'ok') as ok, count(*) filter (where status in ('failed','rejected')) as failed,
         round(percentile_cont(0.95) within group (order by latency_ms)::numeric, 0) as p95_ms
  from app.agent_step group by 1, 2;

-- Argus reads this: data-quality signals per owner (scoped by the bot with the Principal)
create view serving.v_data_quality as
select o.hs_owner_id,
  (select count(*) from gold.deal_health h where h.hs_owner_id = o.hs_owner_id) as open_deals,
  (select count(*) from gold.deal_health h where h.hs_owner_id = o.hs_owner_id and not h.next_step_missing) as open_with_next_step,
  (select count(*) from silver.deal d where d.hs_owner_id = o.hs_owner_id and d.is_lost and not d.is_archived
      and d.closed_at >= now() - interval '24 months') as lost_deals,
  (select count(*) from silver.deal d where d.hs_owner_id = o.hs_owner_id and d.is_lost and not d.is_archived
      and d.closed_at >= now() - interval '24 months'
      and lower(trim(coalesce(d.lost_reason_hs, ''))) not in ('', 'other', 'outro', 'outros')) as lost_with_reason
from silver.owner o;
