-- Day 5: per-user watchlist table (the app uses it after login arrives; safe to run now)
drop table if exists watchlist;
create table watchlist (
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  added_at timestamptz default now(),
  primary key (user_id, symbol)
);
alter table watchlist enable row level security;
create policy "own watchlist read"   on watchlist for select to authenticated using (auth.uid() = user_id);
create policy "own watchlist insert" on watchlist for insert to authenticated with check (auth.uid() = user_id);
create policy "own watchlist delete" on watchlist for delete to authenticated using (auth.uid() = user_id);
