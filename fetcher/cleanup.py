"""Delete old rows so the free database never fills up."""
import datetime as dt
import requests
from fetch_filings import SUPABASE_URL, SUPABASE_KEY

H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "return=minimal"}
ITEM_DAYS, CALL_DAYS = 60, 180


def cut(days):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def delete(table, params):
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}", params=params, headers=H, timeout=60)
    r.raise_for_status()


def main():
    c = cut(ITEM_DAYS)
    delete("items", {"published_at": f"lt.{c}"})
    delete("items", {"published_at": "is.null", "created_at": f"lt.{c}"})
    delete("analyst_calls", {"published_at": f"lt.{cut(CALL_DAYS)}"})
    print(f"[cleanup] removed items older than {ITEM_DAYS} days and calls older than {CALL_DAYS} days")


if __name__ == "__main__":
    main()
