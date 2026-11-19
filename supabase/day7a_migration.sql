-- Day 7, PART A: login + allowlist. Additive and safe: your app keeps working after you run this.
-- >>> Put the two real email addresses below before running. <<<
create table if not exists allowed_emails (email text primary key);
alter table allowed_emails enable row level security;      -- no policies: nobody can read it from the app
insert into allowed_emails (email) values ('wealthwithpriyesh47@gmail.com'), ('jbikash76@gmail.com') on conflict do nothing;

create or replace function is_allowed() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from allowed_emails where lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;
revoke execute on function is_allowed() from public, anon;
grant execute on function is_allowed() to authenticated;

-- logged-in, allowed people can read the shared data (the old anonymous read stays until PART B)
drop policy if exists "auth read items" on items;
create policy "auth read items" on items for select to authenticated using (is_allowed());
drop policy if exists "auth read companies" on companies;
create policy "auth read companies" on companies for select to authenticated using (is_allowed());
drop policy if exists "auth read calls" on analyst_calls;
create policy "auth read calls" on analyst_calls for select to authenticated using (is_allowed());
drop policy if exists "auth read health" on source_health;
create policy "auth read health" on source_health for select to authenticated using (is_allowed());

-- one private watchlist per person
alter table watchlist alter column user_id set default auth.uid();
drop policy if exists "own watchlist read" on watchlist;
drop policy if exists "own watchlist insert" on watchlist;
drop policy if exists "own watchlist delete" on watchlist;
create policy "own watchlist read"   on watchlist for select to authenticated using (auth.uid() = user_id and is_allowed());
create policy "own watchlist insert" on watchlist for insert to authenticated with check (auth.uid() = user_id and is_allowed());
create policy "own watchlist delete" on watchlist for delete to authenticated using (auth.uid() = user_id and is_allowed());

-- source health monitoring
alter table source_health add column if not exists error_since timestamptz;
alter table source_health add column if not exists alerted boolean default false;

-- alerts now belong to a logged-in person
alter table push_subs add column if not exists user_id uuid references auth.users(id) on delete cascade;
create or replace function save_push_sub(p_endpoint text, p_p256dh text, p_auth text,
                                         p_symbols text[], p_watch_min int, p_global_min int)
returns void language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or not is_allowed() then raise exception 'not allowed'; end if;
  if p_endpoint !~ '^https://(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com|[a-z0-9.-]+\.push\.apple\.com|[a-z0-9.-]+\.notify\.windows\.com)/'
     or length(p_endpoint) > 1000 or length(p_p256dh) > 200 or length(p_auth) > 100
     or coalesce(array_length(p_symbols, 1), 0) > 300 then
    raise exception 'invalid subscription';
  end if;
  if not exists (select 1 from push_subs where endpoint = p_endpoint)
     and (select count(*) from push_subs) >= 20 then
    raise exception 'subscription limit reached';
  end if;
  insert into push_subs (endpoint, p256dh, auth, symbols, watch_min, global_min, user_id)
  values (p_endpoint, p_p256dh, p_auth, coalesce(p_symbols, '{}'), coalesce(p_watch_min, 3), coalesce(p_global_min, 7), auth.uid())
  on conflict (endpoint) do update set p256dh = excluded.p256dh, auth = excluded.auth, symbols = excluded.symbols,
    watch_min = excluded.watch_min, global_min = excluded.global_min, user_id = auth.uid(), updated_at = now();
end $$;
create or replace function delete_push_sub(p_endpoint text)
returns void language sql security definer set search_path = public as $$
  delete from push_subs where endpoint = p_endpoint and user_id = auth.uid();
$$;
revoke execute on function save_push_sub(text, text, text, text[], int, int) from public, anon;
revoke execute on function delete_push_sub(text) from public, anon;
grant execute on function save_push_sub(text, text, text, text[], int, int) to authenticated;
grant execute on function delete_push_sub(text) to authenticated;
