-- Read contract for company insights (bot reads only serving.*). Notes are the text the insights engine mines.
create view serving.v_deal_facts as
  select hs_deal_id, hs_owner_id, name, amount, is_open, is_won, is_lost, source as campaign, lost_reason_hs as lost_reason
  from silver.deal where not is_archived;
create view serving.v_deal_notes as
  select a.hs_deal_id, d.hs_owner_id, a.summary as note
  from silver.activity a join silver.deal d using (hs_deal_id)
  where a.activity_type = 'note' and a.summary is not null and not d.is_archived;
