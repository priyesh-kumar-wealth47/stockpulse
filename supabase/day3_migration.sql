-- Day 3: run once in Supabase SQL Editor
alter table items add column if not exists score int default 0;
alter table items add column if not exists signal text default 'neutral';
alter table items add column if not exists category text;
alter table items add column if not exists reason text;
alter table items add column if not exists scored_at timestamptz;
create index if not exists items_score_idx on items (score desc, published_at desc);
