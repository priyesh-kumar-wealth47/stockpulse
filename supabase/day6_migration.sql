-- Day 6: run once in Supabase SQL Editor
create table if not exists analyst_calls (
  call_id text primary key, symbol text not null, broker text not null, rating text, action text,
  target numeric, source text not null, title text, url text, published_at timestamptz,
  created_at timestamptz default now()
);
create index if not exists calls_pub_idx on analyst_calls (published_at desc);
create index if not exists calls_sym_idx on analyst_calls (symbol);
alter table analyst_calls enable row level security;
drop policy if exists "read calls" on analyst_calls;
create policy "read calls" on analyst_calls for select to anon using (true);

create table if not exists push_subs (
  endpoint text primary key, p256dh text not null, auth text not null,
  symbols text[] default '{}', watch_min int default 3, global_min int default 7,
  created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table push_subs enable row level security;   -- no policies: only the functions below and the fetcher can touch it

create or replace function save_push_sub(p_endpoint text, p_p256dh text, p_auth text,
                                         p_symbols text[], p_watch_min int, p_global_min int)
returns void language plpgsql security definer set search_path = public as $$
begin
  if p_endpoint !~ '^https://(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com|[a-z0-9.-]+\.push\.apple\.com|[a-z0-9.-]+\.notify\.windows\.com)/'
     or length(p_endpoint) > 1000 or length(p_p256dh) > 200 or length(p_auth) > 100
     or coalesce(array_length(p_symbols, 1), 0) > 300 then
    raise exception 'invalid subscription';
  end if;
  if not exists (select 1 from push_subs where endpoint = p_endpoint)
     and (select count(*) from push_subs) >= 20 then
    raise exception 'subscription limit reached';
  end if;
  insert into push_subs (endpoint, p256dh, auth, symbols, watch_min, global_min)
  values (p_endpoint, p_p256dh, p_auth, coalesce(p_symbols, '{}'), coalesce(p_watch_min, 3), coalesce(p_global_min, 7))
  on conflict (endpoint) do update set p256dh = excluded.p256dh, auth = excluded.auth,
    symbols = excluded.symbols, watch_min = excluded.watch_min, global_min = excluded.global_min, updated_at = now();
end $$;

create or replace function delete_push_sub(p_endpoint text)
returns void language sql security definer set search_path = public as $$
  delete from push_subs where endpoint = p_endpoint;
$$;
grant execute on function save_push_sub(text, text, text, text[], int, int) to anon;
grant execute on function delete_push_sub(text) to anon;

alter table items add column if not exists alerted_at timestamptz;
update items set alerted_at = now() where alerted_at is null;   -- don't alert on old items
