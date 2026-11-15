"""Send web-push alerts for new strong signals. Needs VAPID_PRIVATE_KEY (GitHub secret)."""
import os, json, datetime as dt
from urllib.parse import urlparse
import requests
from pywebpush import webpush, WebPushException
from fetch_filings import SUPABASE_URL, SUPABASE_KEY, record_health

VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY") or None
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT") or "mailto:you@example.com"
APP_URL = os.environ.get("APP_URL") or "/"
H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
ALLOWED_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", ".push.apple.com", ".notify.windows.com")
LABEL = {"positive": "Positive", "caution": "Caution", "watch": "Watch"}
MAX_PER_SUB = 3


def host_ok(endpoint):
    p = urlparse(endpoint)
    return p.scheme == "https" and any(p.hostname == h or p.hostname.endswith(h) for h in ALLOWED_HOSTS if h)


def stocks(it):
    return {it["symbol"]} if it.get("symbol") else set(it.get("matched_symbols") or [])


def pick_for(sub, items):
    mine = set(sub.get("symbols") or [])
    wmin, gmin = sub.get("watch_min") or 3, sub.get("global_min") or 7
    hit = [i for i in items if (stocks(i) & mine and i["score"] >= wmin) or i["score"] >= gmin]
    return sorted(hit, key=lambda i: -i["score"])


def payload(it):
    name = it.get("company") or ", ".join(sorted(stocks(it))[:2]) or it["source"]
    body = (it.get("summary") or it["title"]).strip()
    return {"title": f"{LABEL.get(it['signal'], 'Signal')} {it['score']}/10: {name}"[:90],
            "body": body[:140] + ("\u2026" if len(body) > 140 else ""),
            "tag": it["external_id"], "url": APP_URL}


def send(sub, data):
    webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
            data=json.dumps(data), vapid_private_key=VAPID_PRIVATE, vapid_claims={"sub": VAPID_SUBJECT}, ttl=3600)


def main():
    if not VAPID_PRIVATE:
        print("[alerts] VAPID_PRIVATE_KEY not set - alerts skipped")
        return
    subs = requests.get(f"{SUPABASE_URL}/rest/v1/push_subs", params={"select": "*"}, headers=H, timeout=30).json()
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = requests.get(f"{SUPABASE_URL}/rest/v1/items", params={
        "select": "external_id,source,symbol,company,title,summary,signal,score,matched_symbols",
        "alerted_at": "is.null", "signal": "in.(positive,caution)", "score": "gte.3",
        "published_at": f"gte.{since}", "order": "score.desc", "limit": 100}, headers=H, timeout=30).json()
    if not isinstance(items, list) or not items:
        print("[alerts] no new signals")
        return
    sent = dead = 0
    for sub in subs if isinstance(subs, list) else []:
        if not host_ok(sub["endpoint"]):
            continue
        todo = pick_for(sub, items)
        msgs = [payload(i) for i in todo[:MAX_PER_SUB]]
        if len(todo) > MAX_PER_SUB:
            msgs.append({"title": f"{len(todo) - MAX_PER_SUB} more signals", "body": "Open StockPulse to see them.", "tag": "more", "url": APP_URL})
        for m in msgs:
            try:
                send(sub, m)
                sent += 1
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                if code in (404, 410):
                    requests.delete(f"{SUPABASE_URL}/rest/v1/push_subs", params={"endpoint": f"eq.{sub['endpoint']}"}, headers=H, timeout=30)
                    dead += 1
                else:
                    print(f"[alerts] push error {code}: {str(e)[:120]}")
                break
    ids = [i["external_id"] for i in items]
    for k in range(0, len(ids), 50):
        chunk = ",".join(ids[k:k + 50])
        requests.patch(f"{SUPABASE_URL}/rest/v1/items", params={"external_id": f"in.({chunk})"},
                       json={"alerted_at": dt.datetime.now(dt.timezone.utc).isoformat()}, headers=H, timeout=30)
    print(f"[alerts] {len(items)} new signals, {sent} notifications sent, {dead} dead subscriptions removed")
    try:
        record_health("Push alerts", "ok", sent)
    except Exception:
        pass


if __name__ == "__main__":
    main()
