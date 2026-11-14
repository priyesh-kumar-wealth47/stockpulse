"""Fetch whitelisted media RSS feeds, match stocks, dedupe, store in Supabase."""
import re, csv, io, html, hashlib, datetime as dt
import requests, feedparser
from fetch_filings import (SUPABASE_URL, SUPABASE_KEY, UA, sb, save_items,
                           record_health)

# WHITELIST: only these feeds are ever read. (publisher, url)
FEEDS = [
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Economic Times", "https://economictimes.indiatimes.com/rssfeeds/1373380680.cms"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Business Standard", "https://www.business-standard.com/rss/companies-101.rss"),
    ("Mint", "https://www.livemint.com/rss/markets"),
    ("Mint", "https://www.livemint.com/rss/companies"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/business.xml"),
    # Reuters has no official RSS; Google News filtered to reuters.com
    ("Reuters", "https://news.google.com/rss/search?q=site:reuters.com+India+(stocks+OR+markets+OR+economy)&hl=en-IN&gl=IN&ceid=IN:en"),
]

SYMBOL_STOP = {"THE", "AND", "FOR", "ALL", "NEW", "TOP", "BUY", "SELL", "IPO", "FII",
               "DII", "GDP", "CPI", "RBI", "SEBI", "NSE", "BSE", "USA", "ETF", "SIP",
               "EPS", "PAT", "AI", "IT", "US", "UK", "GST", "FDI", "LIVE", "NEWS"}
LEGAL = re.compile(r"\b(limited|ltd|pvt|private|inc)\b\.?")
TAIL = re.compile(r"\s+(industries|india|corporation|corp|enterprises|company)$")


def headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def norm_words(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]+", " ", s.lower())).strip()


# ---------- company list (for stock matching) ----------
def db_companies():
    rows, off = [], 0
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/companies",
                         params={"select": "symbol,name", "limit": 1000, "offset": off},
                         headers=headers(), timeout=30)
        r.raise_for_status()
        part = r.json()
        rows += part
        if len(part) < 1000:
            return rows
        off += 1000


def ensure_companies():
    rows = db_companies()
    if rows:
        return rows
    new = []
    try:  # official NSE equity list
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        s.get("https://www.nseindia.com", timeout=20)
        r = s.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", timeout=30)
        r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.text)):
            row = {k.strip(): (v or "").strip() for k, v in row.items()}
            if row.get("SYMBOL") and row.get("NAME OF COMPANY"):
                new.append({"symbol": row["SYMBOL"], "name": row["NAME OF COMPANY"]})
    except Exception as e:
        print(f"[companies] NSE list failed ({e}); using names seen in filings")
        r = requests.get(f"{SUPABASE_URL}/rest/v1/items",
                         params={"select": "symbol,company", "kind": "eq.official", "limit": 1000},
                         headers=headers(), timeout=30)
        r.raise_for_status()
        seen = {x["symbol"]: x["company"] for x in r.json() if x.get("symbol") and x.get("company")}
        new = [{"symbol": k, "name": v} for k, v in seen.items()]
    for i in range(0, len(new), 500):
        sb("companies?on_conflict=symbol", new[i:i + 500],
           "resolution=merge-duplicates,return=minimal")
    print(f"[companies] loaded {len(new)}")
    return new


class Matcher:
    def __init__(self, companies):
        self.alias, self.symbols = {}, {c["symbol"] for c in companies}
        for c in companies:
            full = norm_words(LEGAL.sub("", c["name"].lower()))
            if len(full) >= 4:
                self.alias.setdefault(full, c["symbol"])
            short = TAIL.sub("", full)
            if short != full and len(short) >= 6 and not short.endswith(" of"):
                self.alias.setdefault(short, c["symbol"])
        keys = sorted(self.alias, key=len, reverse=True)
        self.rx = re.compile(r"\b(" + "|".join(map(re.escape, keys)) + r")\b") if keys else None

    def find(self, text):
        found = []
        if self.rx:
            for m in self.rx.findall(norm_words(text)):
                found.append(self.alias[m])
        for w in set(re.findall(r"\b[A-Z][A-Z0-9&]{2,}\b", text)):
            if w in self.symbols and w not in SYMBOL_STOP:
                found.append(w)
        out = list(dict.fromkeys(found))
        return out[:5]


# ---------- feed parsing ----------
def clean(s, n=500):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def entry_time(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    return dt.datetime(*t[:6], tzinfo=dt.timezone.utc).isoformat() if t else None


def parse_feed(publisher, xml, matcher):
    out = []
    for e in feedparser.parse(xml).entries:
        title = clean(e.get("title"), 300)
        if publisher == "Reuters":
            title = re.sub(r"\s+-\s+Reuters$", "", title)
        if not title:
            continue
        body = clean(e.get("summary"))
        key = hashlib.sha1(norm_words(title).encode()).hexdigest()[:20]
        syms = matcher.find(f"{title}. {e.get('summary', '')}" if body else title)
        out.append({
            "external_id": f"MEDIA:{key}", "kind": "media", "source": publisher,
            "symbol": None, "company": None, "title": title,
            "body": body or None, "url": e.get("link"),
            "published_at": entry_time(e), "matched_symbols": syms,
        })
    return out


def main():
    matcher = Matcher(ensure_companies())
    seen, ok = set(), 0
    for publisher, url in FEEDS:
        name = f"{publisher} | {url.split('/')[-1][:30] or url[-30:]}"
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            rows = [x for x in parse_feed(publisher, r.content, matcher)
                    if x["external_id"] not in seen]
            seen.update(x["external_id"] for x in rows)
            save_items(rows)
            record_health(name, "ok", len(rows))
            tagged = sum(1 for x in rows if x["matched_symbols"])
            print(f"[{name}] OK - {len(rows)} items, {tagged} matched to stocks")
            ok += 1
        except Exception as e:
            print(f"[{name}] FAILED - {type(e).__name__}: {e}")
            try:
                record_health(name, "error", 0, str(e)[:300])
            except Exception:
                pass
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
