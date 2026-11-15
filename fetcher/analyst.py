"""Extract broker calls (rating, target price) reported in news articles.
Each call is attributed to the publisher that reported it, never presented as ours."""
import re, hashlib, datetime as dt
import requests
from fetch_filings import SUPABASE_URL, SUPABASE_KEY, sb, record_health

BROKERS = ["Jefferies", "Goldman Sachs", "Morgan Stanley", "Nomura", "CLSA", "Citigroup|Citi", "JP ?Morgan",
 "Kotak Institutional Equities|Kotak Securities|Kotak", "Motilal Oswal", "ICICI Securities", "ICICI Direct",
 "HDFC Securities", "Axis Securities", "Axis Capital", "Axis Direct", "Emkay", "Nuvama", "Elara",
 "Antique Stock Broking|Antique", "Prabhudas Lilladher|PL Capital", "Sharekhan", "Systematix", "Ambit", "UBS",
 "Bernstein", "Macquarie", "BofA Securities|Bank of America|BofA", "Credit Suisse", "Investec", "Edelweiss",
 "IIFL Securities|IIFL", "Anand Rathi", "Choice Broking", "Dolat Capital", "Religare Broking", "Geojit",
 "Centrum", "SBI Securities|SBICAP Securities", "Phillip ?Capital", "Mirae Asset", "Equirus", "JM Financial",
 "Batlivala & Karani|B&K Securities", "DAM Capital", "Ventura Securities|Ventura", "Arihant Capital",
 "Nirmal Bang", "Barclays", "HSBC", "Deutsche Bank", "DBS", "Daiwa", "InCred", "KRChoksey|Kr Choksey",
 "Sunidhi", "LKP Securities", "Asit C Mehta", "Stoxbox"]
BROKER_RX = re.compile(r"\b(" + "|".join(f"(?:{b})" for b in BROKERS) + r")\b")  # case-sensitive: proper nouns
RATING_RX = re.compile(r"\b(strong buy|strong sell|buy|sell|hold|neutral|outperform|underperform|overweight|underweight|"
                       r"accumulate|reduce|equal-?weight|market perform|sector perform)\b", re.I)
RATING_MAP = {"buy": "Buy", "strong buy": "Buy", "outperform": "Buy", "overweight": "Buy", "accumulate": "Buy",
              "sell": "Sell", "strong sell": "Sell", "underperform": "Sell", "underweight": "Sell", "reduce": "Sell",
              "hold": "Hold", "neutral": "Hold", "equal-weight": "Hold", "equalweight": "Hold",
              "market perform": "Hold", "sector perform": "Hold"}
TARGET_RXS = [
    re.compile(r"\btarget(?: price)?\b.{0,40}?\b(?:to|at|of|:)\s*(?:Rs\.?|\u20b9|INR)?\s*([\d,]{2,}(?:\.\d+)?)(?!\s*%)", re.I),
    re.compile(r"(?:Rs\.?|\u20b9)\s*([\d,]{2,}(?:\.\d+)?)\s*(?:target|TP)\b", re.I),
    re.compile(r"\b(?:TP|PT)\b\s*(?:of|at|:)?\s*(?:Rs\.?|\u20b9)?\s*([\d,]{2,}(?:\.\d+)?)", re.I)]
ACTIONS = [
    ("downgrade", re.compile(r"\b(cuts?|lowers?)\b[^.]{0,40}\bto (neutral|hold|sell|reduce|underperform|underweight)\b|\bdowngrad\w*|\b(cuts?|lowers?|slashes?|trims?) (the )?target|target (price )?(cut|lowered|slashed|reduced)", re.I)),
    ("upgrade", re.compile(r"\b(raises?|lifts?)\b[^.]{0,40}\bto (buy|outperform|overweight)\b|\bupgrad\w*|\b(raises?|hikes?|lifts?|increases?) (the )?target|target (price )?(raised|hiked|increased)", re.I)),
    ("initiate", re.compile(r"\binitiat\w* coverage", re.I)),
    ("maintain", re.compile(r"\b(maintains?|retains?|reiterates?|keeps?|stays?)\b", re.I))]
STOP_NAME = {"limited", "ltd", "industries", "india", "corporation", "company", "the", "and", "of"}


def parse_target(s):
    for rx in TARGET_RXS:
        m = rx.search(s)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if 1 <= v <= 1_000_000:
                return v
    return None


def pick_symbol(sentence, bpos, matched, names):
    if len(matched) == 1:
        return matched[0]
    best, bd = None, 10**9
    for s in matched:  # several stocks: take the one mentioned closest to the broker
        keys = [s] + [w for w in re.findall(r"[A-Za-z&]+", names.get(s, ""))[:1] if w.lower() not in STOP_NAME]
        for k in keys:
            for m in re.finditer(r"\b" + re.escape(k) + r"\b", sentence):
                d = abs(m.start() - bpos)
                if d < bd and d <= 120:
                    best, bd = s, d
    return best


def extract(item, names):
    text = f"{item['title']}. {item.get('body') or ''}"
    out, seen = [], set()
    for sent in re.split(r"(?<=[.!?])\s+", text):
        bm = BROKER_RX.search(sent)
        if not bm:
            continue
        rm = RATING_RX.search(sent)
        rating = RATING_MAP.get(rm.group(1).lower().replace(" ", " ")) if rm else None
        target = parse_target(sent)
        action = next((a for a, rx in ACTIONS if rx.search(sent)), "call")
        if not (rating or target) or (rating is None and action in ("call", "maintain")):
            continue
        sym = pick_symbol(sent, bm.start(), item.get("matched_symbols") or [], names)
        if not sym:
            continue
        broker = bm.group(1)
        day = (item.get("published_at") or "")[:10]
        cid = hashlib.sha1(f"{sym}|{broker}|{rating}|{target}|{day}".encode()).hexdigest()[:20]
        if cid in seen:
            continue
        seen.add(cid)
        out.append({"call_id": cid, "symbol": sym, "broker": broker, "rating": rating, "action": action,
                    "target": target, "source": item["source"], "title": item["title"][:300],
                    "url": item.get("url"), "published_at": item.get("published_at")})
    return out


def main():
    H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    names = {}
    off = 0
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/companies", params={"select": "symbol,name", "limit": 1000, "offset": off}, headers=H, timeout=30)
        r.raise_for_status()
        names.update({c["symbol"]: c["name"] for c in r.json()})
        if len(r.json()) < 1000:
            break
        off += 1000
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(f"{SUPABASE_URL}/rest/v1/items", params={
        "select": "external_id,source,title,body,url,published_at,matched_symbols", "kind": "eq.media",
        "published_at": f"gte.{since}", "order": "published_at.desc", "limit": 1000}, headers=H, timeout=60)
    r.raise_for_status()
    calls = {}
    for it in r.json():
        for c in extract(it, names):
            calls.setdefault(c["call_id"], c)
    rows = list(calls.values())
    for i in range(0, len(rows), 200):
        sb("analyst_calls?on_conflict=call_id", rows[i:i + 200], "resolution=ignore-duplicates,return=minimal")
    print(f"[analyst] {len(rows)} broker calls found in last 48h")
    try:
        record_health("Analyst calls", "ok", len(rows))
    except Exception:
        pass


if __name__ == "__main__":
    main()
