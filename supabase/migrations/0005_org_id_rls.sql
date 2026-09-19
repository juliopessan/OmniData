-- D1: single tenant, org_id on every business table. D2/§9: RLS on, with NO policies (service role only).
do $$
declare t record;
begin
  for t in select schemaname, tablename from pg_tables where schemaname in ('silver','app') loop
    execute format('alter table %I.%I add column if not exists org_id uuid not null default %L',
                   t.schemaname, t.tablename, '00000000-0000-0000-0000-000000000001');
  end loop;
  for t in select schemaname, tablename from pg_tables where schemaname in ('bronze','silver','app') loop
    execute format('alter table %I.%I enable row level security', t.schemaname, t.tablename);
  end loop;
end $$;
