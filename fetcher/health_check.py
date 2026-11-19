"""Watches source_health. Sends a push alert when a source has been failing/stale for 45+ minutes
(once), and again when it recovers. Needs the same VAPID secrets as send_alerts.py."""
import json, datetime as dt
import requests
from fetch_filings import SUPABASE_URL, SUPABASE_KEY
import send_alerts as SA

H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
SOFT = {"AI summaries", "Push alerts", "Analyst calls"}   # shown in the app, but no push alert
STALE_MIN, ALERT_AFTER_MIN = 90, 45


def parse(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def evaluate(r, now):
    """Return (patch, message) for one source_health row."""
    last = parse(r.get("last_run"))
    age = (now - last).total_seconds() / 60 if last else 1e9
    bad = r.get("last_status") == "error" or age > STALE_MIN
    since = parse(r.get("error_since"))
    name = r["source"]
    if bad:
        if not since:
            return {"error_since": now.isoformat()}, None
        if (now - since).total_seconds() / 60 >= ALERT_AFTER_MIN and not r.get("alerted") and name not in SOFT:
            why = (r.get("last_error") or "no recent update")[:90]
            return {"alerted": True}, {"title": f"Source problem: {name}", "body": f"Failing for 45+ minutes. {why}", "tag": f"health-{name}", "url": SA.APP_URL}
        return {}, None
    if r.get("alerted"):
        return {"error_since": None, "alerted": False}, {"title": f"{name} is working again", "body": "Data is flowing normally.", "tag": f"health-{name}", "url": SA.APP_URL}
    if since:
        return {"error_since": None, "alerted": False}, None
    return {}, None


def notify(msg):
    subs = requests.get(f"{SUPABASE_URL}/rest/v1/push_subs", params={"select": "*"}, headers=H, timeout=30).json()
    for sub in subs if isinstance(subs, list) else []:
        if SA.host_ok(sub["endpoint"]):
            try:
                SA.send(sub, msg)
            except Exception as e:
                print(f"[health] push failed: {str(e)[:100]}")


def main():
    rows = requests.get(f"{SUPABASE_URL}/rest/v1/source_health", params={"select": "*"}, headers=H, timeout=30).json()
    now = dt.datetime.now(dt.timezone.utc)
    problems = 0
    for r in rows if isinstance(rows, list) else []:
        patch, msg = evaluate(r, now)
        if r.get("last_status") == "error":
            problems += 1
        if msg and SA.VAPID_PRIVATE:
            notify(msg)
        if patch:
            requests.patch(f"{SUPABASE_URL}/rest/v1/source_health", params={"source": f"eq.{r['source']}"}, json=patch, headers=H, timeout=30)
    print(f"[health] checked {len(rows)} sources, {problems} currently failing")


if __name__ == "__main__":
    main()
