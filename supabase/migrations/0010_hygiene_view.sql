-- Read contract for the Coach's fix queue (bot reads only serving.*).
create view serving.v_hygiene_facts as
  select d.hs_deal_id, d.hs_owner_id, d.name, d.amount, d.close_date, d.next_activity_at,
         coalesce(o.is_active, true) as owner_active,
         (select count(*) from silver.activity a where a.hs_deal_id = d.hs_deal_id and a.activity_type = 'note') as note_count
  from silver.deal d
  left join silver.owner o using (hs_owner_id)
  where not d.is_archived and d.is_open;
