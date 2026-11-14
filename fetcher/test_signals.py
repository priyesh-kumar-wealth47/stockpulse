from signals import analyze
# (title, body, kind, has_stock, expected_signal, expected_category or None)
CASES = [
 ("Press Release", "ABC Ltd bags order worth Rs 450 crore from Indian Railways", "official", True, "positive", "order_win"),
 ("Financial Results", "Net profit jumps 42% to Rs 310 crore, record quarterly profit", "official", True, "positive", None),
 ("Outcome of Board Meeting", "Board approves buyback of equity shares at Rs 1500", "official", True, "positive", "buyback"),
 ("Outcome of Board Meeting", "Board recommended interim dividend of Rs 5 per share", "official", True, "positive", "dividend"),
 ("Reliance promoters buy 2 lakh shares in open market", "", "media", True, "positive", "promoter_buy"),
 ("Brokerage upgrades Titan to buy, raises target price to Rs 4,000", "", "media", True, "positive", None),
 ("USFDA approval for Lupin's generic drug", "", "media", True, "positive", "approval"),
 ("Disclosure", "Release of pledge on shares held by promoter", "official", True, "positive", "pledge_release"),
 ("Disclosure", "Promoter pledged 12% shares of the company", "official", True, "caution", "pledge"),
 ("Statutory auditor resigns from XYZ Ltd", "", "media", True, "caution", "auditor_exit"),
 ("SEBI bans promoters of ABC from securities market, imposes penalty", "", "media", True, "caution", "reg_action"),
 ("CRISIL downgrades long-term rating of ABC to BB", "", "media", True, "caution", None),
 ("Financial Results", "Company reports net loss of Rs 120 crore, swings to loss", "official", True, "caution", None),
 ("Intimation", "Delay in submission of financial results for the quarter", "official", True, "caution", "results_delay"),
 ("Broker downgrades Paytm to sell, cuts target price", "", "media", True, "caution", None),
 ("Tata Motors CFO resigns", "", "media", True, "caution", "mgmt_exit"),
 ("Company denies fraud allegations, says report is baseless", "", "media", True, "neutral", None),
 ("Trading Window", "Closure of trading window for designated persons", "official", True, "neutral", "routine"),
 ("Newspaper Publication", "Copy of newspaper publication of results", "official", True, "neutral", "routine"),
 ("Loss of Share Certificates", "Intimation of loss of share certificates", "official", True, "neutral", "routine"),
 ("Block deal: Fund buys 1% stake in ABC", "", "media", True, "watch", "block_deal"),
 ("Sensex ends flat as banks drag", "", "media", False, "neutral", None),
 ("Update", "No pledge has been created by promoters", "official", True, "neutral", None),
 ("RBI cuts repo rate; profit surges for banks", "", "media", False, "positive", None),
 ("Outcome of Board Meeting", "Board approves bonus issue and stock split", "official", True, "positive", "bonus_split"),
 ("Fire at plant halts production at ABC Ltd", "", "media", True, "caution", "ops_halt"),
]
bad = 0
for t, b, k, hs, es, ec in CASES:
    s, sig, cat, why = analyze(t, b, k, hs)
    ok = sig == es and (ec is None or cat == ec)
    bad += not ok
    print(("OK  " if ok else "FAIL"), sig, s, cat, "|", t[:50], "|", why)
print(f"\n{len(CASES)-bad}/{len(CASES)} passed")
raise SystemExit(bad > 0)
