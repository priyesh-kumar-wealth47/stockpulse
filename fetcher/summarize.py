"""Summaries for cards. Always gives a free extractive summary first, then
upgrades the highest-scoring items with a free AI (Gemini, then Groq)."""
import os, re, json, time, datetime as dt
import requests
from fetch_filings import SUPABASE_URL, SUPABASE_KEY, sb, record_health

GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or None
GROQ_KEY = os.environ.get("GROQ_API_KEY") or None
MAX_WORDS, AI_PER_RUN, BATCH = 55, 24, 8
H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
IMPACTS = {"positive", "negative", "neutral", "unclear"}


class RateLimited(Exception):
    pass


# ---------- free extractive summary ----------
def extractive(title, body):
    body = re.sub(r"\s+", " ", body or "").strip()
    base = body if len(body) > 40 else title
    out, words = [], 0
    for sent in re.split(r"(?<=[.!?])\s+", base):
        w = len(sent.split())
        if out and words + w > MAX_WORDS:
            break
        out.append(sent)
        words += w
        if words >= MAX_WORDS:
            break
    text = " ".join(out)
    ws = text.split()
    return " ".join(ws[:MAX_WORDS]) + ("\u2026" if len(ws) > MAX_WORDS else "")


# ---------- AI ----------
def prompt_for(items):
    lines = [f"[{i}] ({it['source']}) {it['title']}. {(it.get('body') or '')[:600]}" for i, it in enumerate(items)]
    return ("You summarise Indian stock-market news for a retail investor.\n"
            f"For each item write a plain-English summary of at most {MAX_WORDS} words using ONLY facts in the text "
            "(never add numbers, names or claims that are not there; no advice or predictions). "
            "Also give impact on the company's stock: positive, negative, neutral or unclear.\n"
            'Reply with JSON only: {"items":[{"id":0,"summary":"...","impact":"positive"}]}\n\nITEMS:\n'
            + "\n".join(lines))


def parse_ai(text, items):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    out = {}
    for x in data.get("items", []):
        try:
            it = items[int(x["id"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        summ = re.sub(r"\s+", " ", str(x.get("summary", ""))).strip()
        src = f"{it['title']} {it.get('body') or ''}".replace(",", "")
        nums = re.findall(r"\d[\d,]*\.?\d*", summ)
        if not summ or any(n.replace(",", "").rstrip(".") not in src for n in nums):
            continue  # reject summaries containing numbers not in the source
        ws = summ.split()
        if len(ws) > MAX_WORDS + 20:
            summ = " ".join(ws[:MAX_WORDS]) + "\u2026"
        imp = str(x.get("impact", "unclear")).lower()
        out[it["external_id"]] = (summ, imp if imp in IMPACTS else "unclear")
    return out


def pick_gemini_models():
    if os.environ.get("GEMINI_MODEL"):
        return [os.environ["GEMINI_MODEL"]]
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                     headers={"x-goog-api-key": GEMINI_KEY}, timeout=30)
    r.raise_for_status()
    names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    bad = ("image", "tts", "live", "audio", "preview", "exp", "embedding", "robotics",
           "computer", "vision", "thinking", "gemma", "learnlm", "aqa")
    ok = [n for n in names if "flash" in n and not any(b in n for b in bad)]
    lite = sorted([n for n in ok if "lite" in n], reverse=True)
    rest = sorted([n for n in ok if "lite" not in n], reverse=True)
    # prefer fixed versions over "-latest" aliases (aliases are often overloaded), keep order otherwise
    ordered = [n for n in lite + rest if "latest" not in n] + [n for n in lite + rest if "latest" in n]
    return ordered[:3]


def call_gemini(items, model):
    for attempt, wait in enumerate((0, 5, 15)):
        time.sleep(wait)
        r = _gemini_request(items, model)
        if r.status_code not in (500, 502, 503, 504):
            break
        print(f"[summaries] {model}: HTTP {r.status_code}, retry {attempt + 1}/3")
    if r.status_code == 429:
        raise RateLimited("gemini")
    r.raise_for_status()
    return parse_ai(r.json()["candidates"][0]["content"]["parts"][0]["text"], items)


def _gemini_request(items, model):
    return requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": GEMINI_KEY},
                      json={"contents": [{"parts": [{"text": prompt_for(items)}]}],
                            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}},
                      timeout=60)


def pick_groq_model():
    if os.environ.get("GROQ_MODEL"):
        return os.environ["GROQ_MODEL"]
    r = requests.get("https://api.groq.com/openai/v1/models",
                     headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=30)
    r.raise_for_status()
    ids = sorted(m["id"] for m in r.json().get("data", []))
    for pref in ("instant", "8b", "llama"):
        for i in ids:
            if pref in i and "whisper" not in i and "guard" not in i:
                return i
    return None


def call_groq(items, model):
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {GROQ_KEY}"},
                      json={"model": model, "temperature": 0.2,
                            "response_format": {"type": "json_object"},
                            "messages": [{"role": "user", "content": prompt_for(items)}]}, timeout=60)
    if r.status_code == 429:
        raise RateLimited("groq")
    r.raise_for_status()
    return parse_ai(r.json()["choices"][0]["message"]["content"], items)


# ---------- database ----------
FIELDS = "external_id,kind,source,title,body,signal,score,reason,category"


def get(params):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/items", params={"select": FIELDS, **params}, headers=H, timeout=60)
    r.raise_for_status()
    return r.json()


def write(rows):
    for i in range(0, len(rows), 200):
        sb("items?on_conflict=external_id", rows[i:i + 200], "resolution=merge-duplicates,return=minimal")


def row_base(r):
    return {k: r.get(k) for k in ("external_id", "kind", "source", "title", "signal", "score", "reason", "category")}


def extractive_pass():
    n = 0
    for _ in range(10):
        rows = get({"summary": "is.null", "order": "id", "limit": 500})
        if not rows:
            break
        write([{**row_base(r), "summary": extractive(r["title"], r.get("body")),
                "summary_source": "extractive"} for r in rows])
        n += len(rows)
    print(f"[summaries] extractive: {n}")


def ai_pass():
    if not (GEMINI_KEY or GROQ_KEY):
        print("[summaries] no AI key set - extractive summaries only")
        return "skipped", 0, None
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    todo = get({"summary_source": "eq.extractive", "signal": "in.(positive,caution,watch)",
                "score": "gte.2", "published_at": f"gte.{since}",
                "order": "score.desc,published_at.desc", "limit": AI_PER_RUN})
    if not todo:
        print("[summaries] nothing to upgrade with AI")
        return "ok", 0, None
    providers = []
    try:
        if GEMINI_KEY:
            for m in pick_gemini_models():
                providers.append(("gemini", call_gemini, m))
        if GROQ_KEY:
            m = pick_groq_model()
            if m:
                providers.append(("groq", call_groq, m))
    except Exception as e:
        print(f"[summaries] model lookup failed: {type(e).__name__}: {e}")
    done, err = 0, None
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        result, used = None, None
        for name, fn, model in list(providers):
            try:
                result, used = fn(batch, model), name
                break
            except RateLimited:
                print(f"[summaries] {name} rate-limited; skipping it this run")
                providers = [p for p in providers if p[0] != name]  # quota is shared per project
            except Exception as e:
                err = f"{name}/{model}: {type(e).__name__}: {str(e)[:150]}"
                print(f"[summaries] {err} - trying next option")
                providers = [p for p in providers if p[2] != model]
        if not providers and result is None:
            break
        if result:
            rows = []
            for r in batch:
                if r["external_id"] in result:
                    summ, imp = result[r["external_id"]]
                    b = row_base(r)
                    if b["signal"] == "watch" and imp in ("positive", "negative"):
                        b["signal"] = "positive" if imp == "positive" else "caution"
                        b["reason"] = f"{b['reason'] or ''} | AI read: {imp}"
                    rows.append({**b, "summary": summ, "summary_source": used, "ai_view": imp})
            write(rows)
            done += len(rows)
        time.sleep(6)  # stay under free per-minute limits
    print(f"[summaries] AI summaries written: {done}")
    return ("ok" if done or not err else "error"), done, err


if __name__ == "__main__":
    extractive_pass()
    status, n, err = ai_pass()
    try:
        record_health("AI summaries", status, n, err)
    except Exception:
        pass
