-- Read contract for the evening recap (alerts/engine.py::evening_recaps): notes/tasks logged today.
create view serving.v_activity as
  select hs_activity_id, activity_type, hs_deal_id, hs_owner_id, occurred_at from silver.activity;
