"""Score items that have no score yet (or ALL items if RESCORE_ALL=true).
Run after editing rules in signals.py to re-rank old items."""
import os, requests
from fetch_filings import SUPABASE_URL, SUPABASE_KEY, sb
from signals import annotate

ALL = os.environ.get("RESCORE_ALL", "").lower() == "true"
H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def pull(offset):
    params = {"select": "external_id,kind,source,title,body,symbol,matched_symbols",
              "order": "id", "limit": 1000}
    if ALL:
        params["offset"] = offset
    else:
        params["scored_at"] = "is.null"
    r = requests.get(f"{SUPABASE_URL}/rest/v1/items", params=params, headers=H, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    total, offset = 0, 0
    for _ in range(30):
        rows = pull(offset)
        if not rows:
            break
        out = []
        for r in rows:
            out.append({"external_id": r["external_id"], "kind": r["kind"],
                        "source": r["source"], "title": r["title"], **annotate(r)})
        for i in range(0, len(out), 200):
            sb("items?on_conflict=external_id", out[i:i + 200],
               "resolution=merge-duplicates,return=minimal")
        total += len(out)
        offset += 1000
        if ALL and len(rows) < 1000:
            break
    print(f"[rescore] scored {total} items")


if __name__ == "__main__":
    main()
