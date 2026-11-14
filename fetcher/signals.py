"""Rule-based signal engine for Indian stock news. Edit RULES to tune.

Each rule: (id, kind, weight, scope, label, regex, exclude_regex)
  kind  : pos (bullish) | neg (caution) | watch (important, direction unclear)
  scope : any | media (only news articles, not exchange filings)
"""
import re, datetime as dt

I = re.I
_AG = r"(?-i:CRISIL|ICRA|CARE|Ind-?Ra|Brickwork|Acuite)|India Ratings|S&P|Moody'?s|Fitch"
PLEDGE_RELEASE = r"\b(releas\w+|revo\w+|revocation|reduc\w+|cessation)\b[^.]{0,30}\bpledg"

RULES = [
 # ---------------- positive ----------------
 ("order_win", "pos", 3, "any", "Order/contract win",
  r"\b(bags?|bagged|wins?|won|secures?|secured|receives?|received|awarded|bagging)\b[^.]{0,80}\b(orders?|contracts?|letters? of (award|intent|acceptance))\b", None),
 ("results_strong", "pos", 3, "any", "Strong results",
  r"\b(record (quarterly )?(profit|revenue|sales|earnings|PAT|ebitda)|(net )?profit (jumps?|surges?|soars?|rises?|climbs?|grows?|doubles?|zooms?|up \d)|(PAT|net profit|profit after tax) (up|rises|grows|jumps)|beats? (street )?(estimates|expectations)|above (street )?estimates|revenue (jumps|surges|rises|up)\b|turns? (profitable|to profit)|swings? to (a )?profit)", None),
 ("buyback", "pos", 3, "any", "Share buyback", r"\bbuy-?back\b", None),
 ("dividend", "pos", 2, "any", "Dividend", r"\bdividend\b", r"\b(no|nil|omit\w*|skips?)\b[^.]{0,15}dividend"),
 ("special_div", "pos", 1, "any", "Special dividend", r"\bspecial dividend\b", None),
 ("bonus_split", "pos", 2, "any", "Bonus/stock split",
  r"\b(bonus (issue|shares?|debentures)|stock split|sub-?division of (equity )?shares?|split of (equity )?shares?)\b", None),
 ("promoter_buy", "pos", 3, "any", "Promoter/insider buying",
  r"\b(promoters?|insiders?)\b[^.]{0,50}\b(buys?|bought|buying|acquires?|acquired|picks? up|(increases?|raises?) (their |its )?stake)\b|\binsider buying\b", None),
 ("pledge_release", "pos", 2, "any", "Promoter pledge released", PLEDGE_RELEASE, None),
 ("broker_up", "pos", 2, "media", "Broker upgrade / bullish call",
  r"\b(upgrades?|upgraded|initiates? coverage with (a )?buy|(raises?|hikes?|lifts?|increases?) (the )?target|target price (raised|hiked|increased)|(maintains?|reiterates?|retains?) (a )?buy|top pick|outperform|overweight)\b", rf"\b({_AG})\b"),
 ("capacity", "pos", 2, "any", "Capacity expansion / capex",
  r"\b(capacity expansion|expands? capacity|new (manufacturing )?(plant|facility|unit)|commission(s|ed|ing) (of )?(a |its |the )?(new )?(plant|unit|facility|line)|capex (of|plan)|capital expenditure of)\b", None),
 ("approval", "pos", 2, "any", "Regulatory approval",
  r"\b(US ?FDA|FDA|CDSCO|DCGI|CCI|DGCA)\b[^.]{0,40}\b(approval|nod|clearance|approves|approved|clears|cleared)\b|\b(receives?|received|gets?|secures?) [^.]{0,30}(approval|licen[cs]e)\b", None),
 ("credit_up", "pos", 2, "any", "Credit rating upgrade",
  rf"\b({_AG})\b[^.]{{0,60}}\b(upgrad\w+|positive outlook)\b", None),
 ("debt_cut", "pos", 2, "any", "Debt reduction", r"\b(debt[- ]free|repays? (its )?debt|reduces? debt|prepays?)\b", None),
 # ---------------- caution ----------------
 ("pledge", "neg", 3, "any", "Promoter pledging",
  r"\bpledg\w*\b[^.]{0,60}\bpromoters?\b|\bpromoters?\b[^.]{0,60}\bpledg\w*\b", PLEDGE_RELEASE),
 ("pledge_invoked", "neg", 4, "any", "Pledge invoked", r"\binvocation of pledge\b|\bpledged shares (invoked|sold)\b", None),
 ("auditor_exit", "neg", 4, "any", "Auditor resignation",
  r"\bauditors?\b[^.]{0,40}\b(resign\w*|quit|steps? down)\b|\bresignation of (the )?(statutory )?auditors?\b", None),
 ("reg_action", "neg", 3, "any", "Regulatory/legal action",
  r"\bSEBI\b[^.]{0,60}\b(orders?|bans?|banned|penalt(y|ies)|fines?|fined|show[- ]cause|probe|investigat\w+|restrains?|debars?|debarred|impounds?)\b|\b(?-i:ED|CBI)\b[^.]{0,30}\b(raids?|searches|probe|summons?|arrests?)\b|\b(income[- ]tax)\b[^.]{0,30}\b(raids?|searches)\b|\bsearch and seizure\b", None),
 ("broker_down", "neg", 2, "media", "Broker downgrade / bearish call",
  r"\b(downgrades?|downgraded)\b|\b(cuts?|lowers?|slashes?|trims?) (the )?target\b|target price (cut|lowered|slashed|reduced)|\b(maintains?|reiterates?|retains?|initiates? (coverage )?with|downgrades? to|cuts? to) (a )?(sell|reduce|underperform|underweight)\b|\bunderperform\b|\bunderweight\b", rf"\b({_AG})\b"),
 ("credit_down", "neg", 3, "any", "Credit rating downgrade",
  rf"\b({_AG})\b[^.]{{0,60}}\b(downgrad\w+|negative outlook|rating watch negative|withdr\w+ (the )?rating)\b", None),
 ("results_delay", "neg", 3, "any", "Delayed results/filing",
  r"\b(delay\w*|postpon\w*|defer\w*)\b[^.]{0,40}\b(results?|financial statements?|filing|annual report)\b|\bfail(s|ed|ure) to (file|submit|publish)\b", None),
 ("mgmt_exit", "neg", 2, "any", "Top management exit",
  r"\bresign\w*\b[^.]{0,50}\b(CEO|CFO|chief (executive|financial|operating) officer|managing director|chairman|COO|independent director|(?-i:MD))\b|\b(CEO|CFO|chairman|(?-i:MD))\b[^.]{0,30}\b(resigns?|quits?|steps? down|exits?)\b", None),
 ("results_weak", "neg", 3, "any", "Weak results",
  r"\b(net loss|loss widens|widened loss|swings? to (a )?loss|slips? into (the )?red|turns? loss-making|reports? (a )?(net )?loss|posts? (a )?(net )?loss|profit (falls?|drops?|plunges?|declines?|slumps?|dips?|tumbles?|sinks?|down \d)|(PAT|net profit) (down|falls?|declines?|drops?)|misses? (street )?(estimates|expectations)|below (street )?estimates|revenue (falls?|declines?|drops?))\b", None),
 ("default_risk", "neg", 4, "any", "Default / insolvency risk",
  r"\b(insolvency|CIRP|bankruptcy|liquidation|winding[- ]up|loan default|defaults? on|defaulted|fails? to repay|missed (a |the )?(payment|repayment|interest))\b", None),
 ("fraud", "neg", 4, "any", "Fraud / forensic concerns",
  r"\b(fraud|forensic audit|misappropriat\w+|diversion of funds|whistle-?blower|embezzl\w+|siphon\w*)\b", r"\b(denies|denied|rejects?|baseless)\b"),
 ("ops_halt", "neg", 2, "any", "Operations halted",
  r"\b(plant|unit|factory|operations?|production)\b[^.]{0,30}\b(shut ?down|shutdown|closure|halted|suspended|fire|lockout|explosion)\b|\b(fire|explosion|lockout)\b[^.]{0,30}\b(plant|unit|factory)\b", None),
 ("surveillance", "neg", 2, "any", "Exchange surveillance / suspension",
  r"\b(?-i:ASM|GSM)\b[^.]{0,20}(stage|framework|list|category)|\b(additional|graded) surveillance measure\b|\btrading suspension\b|\bsuspended from trading\b|\bdelist\w+\b", None),
 ("promoter_sell", "neg", 2, "any", "Promoter selling",
  r"\bpromoters?\b[^.]{0,50}\b(sells?|sold|offloads?|dilutes?|reduces? (their |its )?stake|stake sale|exits?)\b", None),
 ("tax_penalty", "neg", 1, "any", "Tax/penalty notice",
  r"\b((GST|tax|income tax) (demand|notice|penalty)|penalty of|show[- ]cause notice)\b", None),
 # ---------------- watch (important, direction unclear) ----------------
 ("block_deal", "watch", 2, "any", "Bulk/block deal", r"\b(bulk deal|block deal)\b", None),
 ("ma", "watch", 2, "any", "M&A / stake deal",
  r"\b(acquires?|acquisition|to acquire|merger|demerger|amalgamation|takeover|open offer|stake sale)\b", None),
 ("fundraise", "watch", 1, "any", "Fundraising",
  r"\b(QIP|qualified institutional placement|rights issue|preferential (issue|allotment)|fund[- ]?raising|FPO|offer for sale|(?-i:OFS)|warrants)\b", None),
 ("results_due", "watch", 1, "any", "Results/board meeting due",
  r"\bboard meeting\b[^.]{0,80}\b(results|financial)\b", None),
]

NOISE = re.compile(
    r"\b(trading window|newspaper publication|loss of share certificates?|duplicate share|"
    r"annual general meeting|postal ballot|book closure|regulation 40|compliance certificate|"
    r"investor (meet|presentation)|analyst/?institutional investor|schedule of (analyst|investor)|"
    r"(?-i:AGM))\b", I)
NEGATE = re.compile(r"\b(no|not|nil|denies|denied|without|rejects?)\b[^.;]{0,25}$", I)

_COMPILED = [(i, k, w, sc, lab, re.compile(p, I), re.compile(x, I) if x else None)
             for i, k, w, sc, lab, p, x in RULES]


def analyze(title, body, kind, has_stock):
    text = f"{title or ''}. {(body or '')[:1500]}"
    hits = []  # (kind, weight, id, label, snippet)
    for rid, k, w, scope, label, rx, ex in _COMPILED:
        if scope == "media" and kind != "media":
            continue
        if ex and ex.search(text):
            continue
        for m in rx.finditer(text):
            if NEGATE.search(text[max(0, m.start() - 30):m.start()]):
                continue
            hits.append((k, w, rid, label, m.group(0)[:70].strip()))
            break
    pos = sum(h[1] for h in hits if h[0] == "pos")
    neg = sum(h[1] for h in hits if h[0] == "neg")
    watch = sum(h[1] for h in hits if h[0] == "watch")
    strong = any(h[1] >= 2 and h[0] != "watch" for h in hits)
    if NOISE.search(text) and not strong:
        return 0, "neutral", "routine", None
    net = pos - neg
    if net != 0:
        sig, side = ("positive", "pos") if net > 0 else ("caution", "neg")
        mag = min(10, abs(net))
        if kind == "official":
            mag = min(10, mag + 1)       # confirmed exchange filing
        if kind == "media" and not has_stock:
            mag = max(1, mag // 2)       # market-wide, not about one stock
    elif pos and neg:
        sig, side, mag = "watch", None, 2   # mixed signals
    elif watch:
        sig, side, mag = "watch", "watch", min(watch, 4)
    else:
        return 0, "neutral", None, None
    pick = sorted([h for h in hits if side is None or h[0] == side], key=lambda h: -h[1]) if side else sorted(hits, key=lambda h: -h[1])
    reason = "; ".join(f"{h[3]}: \u201c{h[4]}\u201d" for h in pick[:2])
    if side is None:
        reason = "Mixed signals - " + reason
    return mag, sig, pick[0][2], reason


def annotate(row):
    score, sig, cat, reason = analyze(
        row.get("title"), row.get("body"), row.get("kind", "official"),
        bool(row.get("symbol") or row.get("matched_symbols")))
    return {"score": score, "signal": sig, "category": cat, "reason": reason,
            "scored_at": dt.datetime.now(dt.timezone.utc).isoformat()}
