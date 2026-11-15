"""1) Score items without a score (or ALL if RESCORE_ALL=true).
2) Corroboration: raise the score when several independent sources report the
   same kind of signal on the same stock in the last 48h."""
import os, datetime as dt
import requests
from fetch_filings import SUPABASE_URL, SUPABASE_KEY, sb
from signals import annotate

ALL = os.environ.get("RESCORE_ALL", "").lower() == "true"
H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def get(params):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/items", params=params, headers=H, timeout=60)
    r.raise_for_status()
    return r.json()


def upsert(rows):
    for i in range(0, len(rows), 200):
        sb("items?on_conflict=external_id", rows[i:i + 200],
           "resolution=merge-duplicates,return=minimal")


def score_pass():
    total, offset = 0, 0
    for _ in range(30):
        params = {"select": "external_id,kind,source,title,body,symbol,matched_symbols",
                  "order": "id", "limit": 1000}
        if ALL:
            params["offset"] = offset
        else:
            params["scored_at"] = "is.null"
        rows = get(params)
        if not rows:
            break
        upsert([{"external_id": r["external_id"], "kind": r["kind"], "source": r["source"],
                 "title": r["title"], **annotate(r)} for r in rows])
        total += len(rows)
        offset += 1000
        if ALL and len(rows) < 1000:
            break
    print(f"[rescore] scored {total} items")


def corroboration(rows):
    """rows: dicts with source, symbol, matched_symbols, signal, category, score_base.
    Returns {external_id: (new_score, sources_count)} for rows that need an update."""
    groups = {}
    for r in rows:
        for st in ([r["symbol"]] if r.get("symbol") else []) + (r.get("matched_symbols") or []):
            groups.setdefault((st, r["signal"], r.get("category")), set()).add(r["source"])
    out = {}
    for r in rows:
        stocks = ([r["symbol"]] if r.get("symbol") else []) + (r.get("matched_symbols") or [])
        n = max([len(groups[(st, r["signal"], r.get("category"))]) for st in stocks] or [1])
        base = r.get("score_base") if r.get("score_base") is not None else r["score"]
        new = min(10, base + (0 if n < 2 else 1 if n == 2 else 2))
        if new != r["score"] or n != (r.get("sources_count") or 1):
            out[r["external_id"]] = (new, n)
    return out


def corroborate_pass():
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = get({"select": "external_id,kind,source,title,symbol,matched_symbols,signal,category,score,score_base,sources_count",
                "signal": "in.(positive,caution)", "published_at": f"gte.{since}",
                "order": "published_at.desc", "limit": 1000})
    changes = corroboration(rows)
    by_id = {r["external_id"]: r for r in rows}
    upsert([{"external_id": k, "kind": by_id[k]["kind"], "source": by_id[k]["source"],
             "title": by_id[k]["title"], "score": sc, "score_base": by_id[k].get("score_base") or by_id[k]["score"],
             "sources_count": n} for k, (sc, n) in changes.items()])
    print(f"[corroborate] updated {len(changes)} of {len(rows)} recent signals")


if __name__ == "__main__":
    score_pass()
    corroborate_pass()
