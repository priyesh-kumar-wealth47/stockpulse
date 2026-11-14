-- Run this once in Supabase: SQL Editor > New query > Run
create table if not exists items (
  id bigint generated always as identity primary key,
  external_id text unique not null,
  kind text not null default 'official',      -- 'official' | 'media'
  source text not null,                       -- 'NSE' | 'BSE' (later: ET, Mint...)
  symbol text,
  company text,
  title text not null,
  body text,
  url text,
  published_at timestamptz,
  created_at timestamptz default now()
);
create index if not exists items_pub_idx on items (published_at desc);
create index if not exists items_symbol_idx on items (symbol);

create table if not exists watchlist (
  symbol text primary key,
  added_at timestamptz default now()
);

create table if not exists source_health (
  source text primary key,
  last_run timestamptz,
  last_status text,        -- 'ok' | 'error'
  last_count int,
  last_error text
);

-- Personal app: the web page may read; only the fetcher (service key) writes.
alter table items enable row level security;
alter table watchlist enable row level security;
alter table source_health enable row level security;
create policy "read items" on items for select to anon using (true);
create policy "read watchlist" on watchlist for select to anon using (true);
create policy "read health" on source_health for select to anon using (true);
