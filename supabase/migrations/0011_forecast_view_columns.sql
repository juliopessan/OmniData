-- The forecast reads creation dates to say whether a predictive model could ever be trained (bot reads only serving.*).
create or replace view serving.v_deal_facts as
  select hs_deal_id, hs_owner_id, name, amount, is_open, is_won, is_lost, source as campaign, lost_reason_hs as lost_reason, created_at, close_date
  from silver.deal where not is_archived;
