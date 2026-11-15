-- Day 4: run once in Supabase SQL Editor
alter table items add column if not exists summary text;
alter table items add column if not exists summary_source text;
alter table items add column if not exists ai_view text;
alter table items add column if not exists score_base int;
alter table items add column if not exists sources_count int default 1;
update items set score_base = score where score_base is null;
create index if not exists items_summary_idx on items (summary_source);
