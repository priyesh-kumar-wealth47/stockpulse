"""Fetch NSE corporate announcements and store them in Supabase."""
import os, sys, hashlib, datetime as dt
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def parse_dt(s, fmts):
    s = (s or "").strip().split(".")[0]
    for f in fmts:
        try:
            return dt.datetime.strptime(s, f).replace(tzinfo=IST).isoformat()
        except ValueError:
            continue
    return None


def make_id(prefix, *parts):
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


def fetch_nse():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    })
    s.get("https://www.nseindia.com", timeout=20)  # sets required cookies
    url = "https://www.nseindia.com/api/corporate-announcements"
    today = dt.datetime.now(IST)
    dated = {"index": "equities",
             "from_date": (today - dt.timedelta(days=1)).strftime("%d-%m-%Y"),
             "to_date": today.strftime("%d-%m-%Y")}
    try:  # date range returns far more than the latest 20
        r = s.get(url, params=dated, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception:
        r = s.get(url, params={"index": "equities"}, timeout=30)
        r.raise_for_status()
        data = r.json()
    out = []
    for a in data:
        title = (a.get("desc") or "").strip()
        if not title:
            continue
        out.append({
            "external_id": make_id("NSE", a.get("seq_id") or "", a.get("symbol"),
                                   a.get("an_dt"), title),
            "kind": "official", "source": "NSE",
            "symbol": a.get("symbol"), "company": a.get("sm_name"),
            "title": title, "body": (a.get("attchmntText") or "").strip() or None,
            "url": a.get("attchmntFile") or None,
            "published_at": parse_dt(a.get("an_dt"), ["%d-%b-%Y %H:%M:%S"]),
        })
    return out


def sb(path, rows, prefer):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Content-Type": "application/json", "Prefer": prefer}
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{path}", json=rows, headers=h, timeout=60)
    r.raise_for_status()


def save_items(rows):
    for i in range(0, len(rows), 200):
        sb("items?on_conflict=external_id", rows[i:i + 200],
           "resolution=ignore-duplicates,return=minimal")


def record_health(source, status, count, error=None):
    sb("source_health?on_conflict=source", [{
        "source": source, "last_run": dt.datetime.now(dt.timezone.utc).isoformat(),
        "last_status": status, "last_count": count, "last_error": error}],
       "resolution=merge-duplicates,return=minimal")


def main():
    ok = 0
    for name, fn in (("NSE", fetch_nse),):
        try:
            rows = fn()
            save_items(rows)
            record_health(name, "ok", len(rows))
            print(f"[{name}] OK - {len(rows)} announcements fetched")
            ok += 1
        except Exception as e:  # one source failing must not stop the other
            print(f"[{name}] FAILED - {type(e).__name__}: {e}")
            try:
                record_health(name, "error", 0, str(e)[:300])
            except Exception as e2:
                print(f"[{name}] could not record health: {e2}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
