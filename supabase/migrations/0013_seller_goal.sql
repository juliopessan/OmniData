-- Personal goal tracking (Aurora): a seller-defined, measurable goal — never a free-form objective the LLM would have to
-- judge as done or not. set_goal expires any prior active goal before inserting the new one (one active goal at a time).
create table app.seller_goal (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app.app_user, hs_owner_id text not null,
  goal_type text not null check (goal_type in ('deals_won', 'quota_pct')),
  target numeric(10,2) not null, deadline date not null,
  status text not null default 'active' check (status in ('active', 'expired')),
  created_at timestamptz not null default now()
);
create index on app.seller_goal (user_id, status);
alter table app.seller_goal enable row level security;

-- repo.py reads serving.* only (its own contract); this view is the read side of app.seller_goal.
create view serving.v_seller_goal as
  select id, user_id, hs_owner_id, goal_type, target, deadline, status, created_at from app.seller_goal;
