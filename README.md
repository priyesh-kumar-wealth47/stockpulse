# StockPulse – Day 1
1. Supabase: create project, run `supabase/schema.sql` in the SQL Editor.
2. GitHub: push this folder to a new repo. Settings > Secrets > Actions, add
   SUPABASE_URL and SUPABASE_SERVICE_KEY (service_role key; keep it secret).
3. Actions tab > "Fetch filings" > Run workflow. Open the log and check NSE/BSE lines.
4. Edit web/config.js (URL + anon key). Deploy the `web` folder on Netlify (drag and drop).
