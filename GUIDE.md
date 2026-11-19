# StockPulse maintenance guide

## How it fits together
- **GitHub Actions** runs every ~15 minutes: fetch NSE filings, fetch news feeds, score items, write summaries,
  find analyst calls, send alerts, check source health, delete old data. Open Actions > "Fetch filings and news" to see logs.
- **Supabase** stores everything and handles sign-in. **Netlify** serves the app (the `web` folder).
- Free tiers throughout. Nothing here costs money unless you add a paid service.

## Secrets and settings (GitHub > Settings > Secrets and variables > Actions)
SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT. Optional variable: GEMINI_MODEL.
`web/config.js` holds only public values (Supabase URL, anon key, VAPID public key). Never put the service key or the VAPID private key in any file.

## Is it healthy?
Open the app: the dot next to the logo is green (all fine), amber (a feed has a problem) or red (NSE has a problem). Tap it for details.
You also get a push alert when a source has failed for 45+ minutes. If the dot is stale-red and no alert came, check that the workflow is still enabled (see "Things that stop silently").

## Common jobs
- **A news feed keeps failing (HTTP 403):** the publisher blocks GitHub's servers. Remove that line from FEEDS in `fetcher/fetch_media.py`,
  or replace it with a Google News search feed like the Reuters one. Push the change.
- **Change how signals are scored:** edit RULES in `fetcher/signals.py`, run `python fetcher/test_signals.py` locally, push,
  then run the workflow with "Re-score ALL items" ticked.
- **Add or remove a person:** Supabase > Authentication > Users > Add user (tick auto-confirm), then in SQL Editor:
  `insert into allowed_emails values ('new@example.com');` To remove: delete the user in Authentication > Users and run
  `delete from allowed_emails where email = 'old@example.com';` Their saved watchlist and alerts are deleted with them.
- **Alerts too noisy or too quiet:** each person changes the score thresholds in the app (filter icon > Alerts).
- **Bad deploy:** Netlify > Deploys > pick an earlier deploy > Publish deploy.

## Things that stop silently (free-tier rules)
- GitHub turns off scheduled workflows after 60 days without repository activity. If the dot goes stale, open Actions and re-enable the
  workflow, or push any small change. Pushing a small edit every month or two avoids it.
- Supabase pauses a free project after about a week with no activity. The 15-minute fetcher keeps it awake; if it pauses, click Restore.
- Gemini's free limits change. If summaries stop being AI-written, the app keeps working with free extractive summaries.
- Supabase's built-in email sender is limited to a few codes per hour. If sign-in codes stop arriving, add a free custom SMTP sender
  (Authentication > Emails > SMTP settings).

## Data kept
News and filings older than 60 days and analyst calls older than 180 days are deleted automatically to stay inside the free database size.

## Reminder
StockPulse highlights what to read. Signals are keyword rules, summaries can contain mistakes, and analyst calls are reported by publishers.
Always check the original source before you act. Nothing here is investment advice.
