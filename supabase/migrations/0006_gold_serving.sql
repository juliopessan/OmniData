-- M1 read contract. Bot code reads ONLY serving.* and app.* (§9). Gold is plain SQL views for now (ADR 0002).

create view gold.stage_benchmarks as
select h.hs_pipeline_id, h.hs_stage_id,
       percentile_cont(0.5)  within group (order by extract(epoch from (h.exited_at - h.entered_at)) / 86400) as median_days,
       percentile_cont(0.75) within group (order by extract(epoch from (h.exited_at - h.entered_at)) / 86400) as p75_days,
       count(*) as n
from silver.deal_stage_history h
join silver.deal d using (hs_deal_id)
where h.exited_at is not null and not d.is_open and d.closed_at >= now() - interval '12 months'
group by 1, 2;

create view gold.deal_health as
with cur as (
  select d.*, s.probability as stage_prob, s.label as stage_label, s.display_order as stage_order,
         (select max(h.entered_at) from silver.deal_stage_history h
           where h.hs_deal_id = d.hs_deal_id and h.hs_stage_id = d.hs_stage_id) as stage_entered_at,
         coalesce(d.last_activity_at,
                  (select max(a.occurred_at) from silver.activity a where a.hs_deal_id = d.hs_deal_id),
                  d.created_at) as last_touch
  from silver.deal d
  join silver.stage s using (hs_pipeline_id, hs_stage_id)
  where d.is_open and not d.is_archived
), calc as (
  select cur.*,
         extract(epoch from now() - coalesce(stage_entered_at, created_at)) / 86400 as days_in_stage,
         coalesce(case when b.n >= 30 then b.p75_days end, 14) as stage_p75_days,   -- 14 = STAGE_AGE_DEFAULT_DAYS
         extract(epoch from now() - last_touch) / 86400 as days_since_activity,
         not exists (select 1 from silver.activity a where a.hs_deal_id = cur.hs_deal_id and (
             (a.activity_type = 'task' and coalesce(a.is_completed, false) = false and a.due_at between now() and now() + interval '7 days')
             or (a.activity_type = 'meeting' and a.occurred_at > now()))) as next_step_missing,
         coalesce(cur.close_date < now(), false) as close_date_overdue,
         (select case when o.old > 0 then (cur.amount - o.old) / o.old end from (
             select nullif(pc.new_value, '')::numeric as old from silver.deal_property_change pc
              where pc.hs_deal_id = cur.hs_deal_id and pc.property = 'amount' and pc.changed_at <= now() - interval '30 days'
              order by pc.changed_at desc limit 1) o) as amount_change_pct_30d
  from cur left join gold.stage_benchmarks b using (hs_pipeline_id, hs_stage_id)
), flags as (
  select calc.*, (days_in_stage > stage_p75_days) as is_stalled from calc
)
select hs_deal_id, name, amount, hs_owner_id, hs_pipeline_id, hs_stage_id, stage_label, stage_order, stage_prob,
       round(days_in_stage::numeric, 1) as days_in_stage, round(stage_p75_days::numeric, 1) as stage_p75_days,
       is_stalled, round(days_since_activity::numeric, 1) as days_since_activity, next_step_missing,
       close_date_overdue, close_date, close_date_pushes, amount_change_pct_30d,
       array_remove(array[
         case when is_stalled then 'stalled' end,
         case when next_step_missing then 'no_next_step' end,
         case when close_date_overdue then 'close_date_overdue' end,
         case when days_since_activity >= 10 then 'gone_quiet' end,
         case when abs(coalesce(amount_change_pct_30d, 0)) > 0.2 then 'amount_swing' end], null) as health_flags,
       coalesce(amount, 0) * coalesce(stage_prob, 0) * least(1.0,
         0.25 + case when is_stalled then 0.3 else 0 end + case when close_date_overdue then 0.25 else 0 end
              + case when next_step_missing then 0.2 else 0 end) as attention_score
from flags;

create view gold.rep_period_metrics as
with periods as (
  select hs_owner_id, date_trunc('month', closed_at)::date as period_start from silver.deal
   where not is_open and not is_archived and closed_at is not null
  union select hs_owner_id, date_trunc('month', period_start)::date from silver.quota
), agg as (
  select p.hs_owner_id, p.period_start,
         (p.period_start + interval '1 month')::date as period_end,
         count(d.*) filter (where d.is_won) as won_count, count(d.*) filter (where d.is_lost) as lost_count,
         coalesce(sum(d.amount) filter (where d.is_won), 0) as won_amount,
         avg(d.amount) filter (where d.is_won) as avg_deal_size,
         percentile_cont(0.5) within group (order by extract(epoch from (d.closed_at - d.created_at)) / 86400)
           filter (where d.is_won) as median_cycle_days
  from periods p
  left join silver.deal d on d.hs_owner_id = p.hs_owner_id and not d.is_open and not d.is_archived
       and d.closed_at >= p.period_start and d.closed_at < (p.period_start + interval '1 month')
  group by 1, 2
), q as (
  select hs_owner_id, date_trunc('month', period_start)::date as period_start, sum(amount) as quota_amount
  from silver.quota group by 1, 2
), w as (
  select a.*, q.quota_amount, (a.won_count + a.lost_count) as n,
         case when a.won_count + a.lost_count > 0 then a.won_count::numeric / (a.won_count + a.lost_count) end as win_rate,
         coalesce((select sum(o.amount) from silver.deal o where o.hs_owner_id = a.hs_owner_id and o.is_open and not o.is_archived
                    and o.close_date >= a.period_start and o.close_date < a.period_end), 0) as open_amount_in_period
  from agg a left join q using (hs_owner_id, period_start)
)
select hs_owner_id, period_start, period_end, won_count, lost_count, won_amount, win_rate,
       case when n > 0 then round(((win_rate + 3.8416 / (2 * n) - 1.96 * sqrt((win_rate * (1 - win_rate) + 3.8416 / (4 * n)) / n)) / (1 + 3.8416 / n))::numeric, 4) end as win_rate_ci_low,
       case when n > 0 then round(((win_rate + 3.8416 / (2 * n) + 1.96 * sqrt((win_rate * (1 - win_rate) + 3.8416 / (4 * n)) / n)) / (1 + 3.8416 / n))::numeric, 4) end as win_rate_ci_high,
       (n < 20) as low_n,                                          -- 20 = MIN_N_RANKING
       round(avg_deal_size, 2) as avg_deal_size, round(median_cycle_days::numeric, 1) as median_cycle_days,
       quota_amount,
       case when quota_amount > 0 then round(won_amount / quota_amount, 4) end as attainment,
       case when quota_amount is not null then greatest(quota_amount - won_amount, 0) end as gap,
       open_amount_in_period,
       case when quota_amount is not null and quota_amount - won_amount > 0
            then round(open_amount_in_period / (quota_amount - won_amount), 2) end as coverage,
       case when win_rate > 0 then round(1 / win_rate, 2) end as required_coverage
from w;

-- ===== serving: the stable read contract (additive changes only) =====
create view serving.v_deal_health as select * from gold.deal_health;
create view serving.v_rep_kpis as select * from gold.rep_period_metrics;
create view serving.v_coverage as
  select hs_owner_id, period_start, quota_amount, won_amount, gap, open_amount_in_period, coverage, required_coverage
  from gold.rep_period_metrics;
create view serving.v_alert_effectiveness as
  select rule_key, count(*) filter (where sent_at is not null) as sent,
         count(*) filter (where viewed_at is not null) as viewed,
         count(*) filter (where acted_at is not null) as acted,
         round(count(*) filter (where acted_at is not null)::numeric
               / nullif(count(*) filter (where sent_at is not null), 0), 3) as action_rate
  from app.alert_event group by 1;
create view serving.v_cost_per_user as
  select user_id, date_trunc('month', created_at)::date as month, count(*) as calls,
         sum(input_tokens) as input_tokens, sum(output_tokens) as output_tokens, sum(cost_usd) as llm_cost_usd
  from app.llm_call group by 1, 2;

-- Metadata for who owns which deal is needed by the bot's scoped lookups
create view serving.v_owner as select hs_owner_id, first_name, last_name, is_active from silver.owner;
