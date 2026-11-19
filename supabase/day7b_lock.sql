-- Day 7, PART B: LOCK THE DATABASE. Run this ONLY after you have signed in successfully on the new app.
-- After this, anyone without an allowed login sees nothing, even with the public key.
drop policy if exists "read items" on items;
drop policy if exists "read companies" on companies;
drop policy if exists "read calls" on analyst_calls;
drop policy if exists "read health" on source_health;
delete from push_subs where user_id is null;   -- old anonymous alert subscriptions; turn alerts on again after login
