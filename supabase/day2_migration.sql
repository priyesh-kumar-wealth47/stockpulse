-- Day 2: run once in Supabase SQL Editor
alter table items add column if not exists matched_symbols text[] default '{}';
create index if not exists items_kind_idx on items (kind);

create table if not exists companies (
  symbol text primary key,
  name text not null
);
alter table companies enable row level security;
create policy "read companies" on companies for select to anon using (true);

delete from source_health where source = 'BSE';
