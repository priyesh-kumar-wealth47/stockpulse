(() => {
"use strict";
const { SUPABASE_URL: U, SUPABASE_ANON_KEY: K } = window.CONFIG || {};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qa = s => String(s).replace(/["\\]/g, "\\$&");
const safeUrl = u => (/^https?:\/\//i.test(u || "") ? u : "");
const store = {
  get(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
};
const reduceMotion = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
const FIELDS = "external_id,kind,source,symbol,company,title,body,summary,summary_source,url,published_at,matched_symbols,signal,score,reason,sources_count";
const PAGE = 25;
const DEFAULTS = { signal: "all", kind: "all", sector: "all", minScore: 3, days: 3, sort: "score" };
const STAR = '<svg viewBox="0 0 24 24"><path d="M12 4l2.5 5.2 5.7.8-4.1 4 1 5.7L12 17l-5.1 2.7 1-5.7-4.1-4 5.7-.8z"/></svg>';
const CHECK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const LABEL = { positive: "Positive", caution: "Caution", watch: "Watch", neutral: "" };

// ---------- sectors (estimated from company names) ----------
const SECTOR_RULES = [
  ["Financials", /\b(bank|finance|financial|finserv|capital|insurance|assurance|credit|microfin|asset management|securities|broking|exchange)\b/i],
  ["IT & Tech", /(infotech|software|technolog|\btech\b|systems|digital|cyber|computers|cloud|semiconductor|consultancy|infosys|wipro)/i],
  ["Pharma & Health", /(pharma|\blabs?\b|laborator|healthcare|hospital|life ?sciences|biotech|drugs|medic|diagnostic|therapeutic|cipla|biocon)/i],
  ["Auto", /(\bmotors?\b|\bauto\b|automotive|automobile|\btyres?\b|\btires?\b|vehicles|two wheelers)/i],
  ["Energy & Power", /(\bpower\b|energy|\boil\b|\bgas\b|petro|\bcoal\b|solar|renewable|\bwind\b|refiner|electric|reliance industries)/i],
  ["Metals & Mining", /(steel|metal|alumin|copper|\bzinc\b|\biron\b|mining|mineral|alloys?|ferro|hindalco|vedanta)/i],
  ["Chemicals", /(chemical|fertili[sz]er|pesticide|agrochem|specialty|polymer|plastic|\bdyes?\b)/i],
  ["Realty", /(realty|real estate|estates|developers|properties)/i],
  ["Infra & Capital goods", /(cement|infra|construct|engineering|projects?|railway|\broads?\b|\bports?\b|logistic|shipping|airport|larsen|\bbuild)/i],
  ["Consumer", /(foods?|beverage|consumer|tobacco|dabur|nestle|britannia|dairy|sugar|\btea\b|coffee|agro|agri|retail|fashion|apparel|textile|jewel|paints?|unilever|\bitc\b)/i],
  ["Telecom & Media", /(telecom|communication|airtel|vodafone|media|entertainment|broadcast|network|cable)/i]
];
const SECTORS = [...SECTOR_RULES.map(r => r[0]), "Others"];
const sectorOf = name => { for (const [s, rx] of SECTOR_RULES) if (rx.test(name || "")) return s; return "Others"; };

// ---------- state ----------
const state = {
  tab: "opps", f: { ...DEFAULTS, ...store.get("sp_filters", {}) }, items: [], seen: new Set(),
  offset: 0, done: false, loading: false, gen: 0, loadedAt: 0,
  watch: store.get("sp_watch", []).filter(s => /^[A-Z0-9&-]+$/.test(s)),
  names: {}, sect: {}, companies: [], ready: Promise.resolve(),
  call: { rating: "all", mine: false, ...store.get("sp_call", {}) },
  alerts: { watchMin: 3, globalMin: 7, ...store.get("sp_alerts", {}) }, theme: store.get("sp_theme", "auto")
};
const feed = $("#feed");

// ---------- data ----------
async function api(path) {
  const r = await fetch(`${U}/rest/v1/${path}`, { headers: { apikey: K, Authorization: `Bearer ${K}` } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
const sinceISO = d => new Date(Date.now() - d * 864e5).toISOString();
function buildQuery() {
  if (state.tab === "calls") {
    const q = ["select=*", `published_at=gte.${encodeURIComponent(sinceISO(7))}`, "order=published_at.desc.nullslast"];
    if (state.call.rating !== "all") q.push(`rating=eq.${state.call.rating}`);
    if (state.call.mine && state.watch.length) q.push(`symbol=in.(${state.watch.map(encodeURIComponent).join(",")})`);
    q.push(`limit=${PAGE}`, `offset=${state.offset}`);
    return `analyst_calls?${q.join("&")}`;
  }
  const f = state.f, p = [`select=${FIELDS}`];
  const sectorMode = f.sector !== "all";
  if (state.tab === "opps") {
    p.push(f.signal === "all" ? "signal=neq.neutral" : `signal=eq.${f.signal}`, `score=gte.${f.minScore}`,
      `published_at=gte.${encodeURIComponent(sinceISO(f.days))}`);
    p.push(f.sort === "latest" ? "order=published_at.desc.nullslast" : "order=score.desc,published_at.desc.nullslast");
  } else {
    if (state.tab === "browse") p.push(`published_at=gte.${encodeURIComponent(sinceISO(f.days))}`);
    if (f.signal !== "all") p.push(`signal=eq.${f.signal}`);
    if (state.tab === "watch") {
      const w = state.watch.map(encodeURIComponent).join(",");
      p.push(`or=(symbol.in.(${w}),matched_symbols.ov.{${w}})`);
    }
    p.push("order=published_at.desc.nullslast");
  }
  if (f.kind !== "all") p.push(`kind=eq.${f.kind}`);
  p.push(`limit=${sectorMode ? 300 : PAGE}`, `offset=${sectorMode ? 0 : state.offset}`);
  return `items?${p.join("&")}`;
}
async function loadCompanies() {
  const setAll = rows => {
    state.companies = rows;
    for (const c of rows) { state.names[c.symbol] = c.name; state.sect[c.symbol] = sectorOf(c.name); }
  };
  const c = store.get("sp_companies", null);
  if (c && Date.now() - c.t < 864e5) return setAll(c.rows);
  let rows = [], off = 0;
  for (;;) {
    const part = await api(`companies?select=symbol,name&order=symbol&limit=1000&offset=${off}`);
    rows = rows.concat(part);
    if (part.length < 1000) break;
    off += 1000;
  }
  store.set("sp_companies", { t: Date.now(), rows });
  setAll(rows);
}

// ---------- rendering ----------
function ago(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60) return "just now";
  const m = s / 60; if (m < 60) return `${Math.floor(m)}m ago`;
  const h = m / 60; if (h < 24) return `${Math.floor(h)}h ago`;
  const d = h / 24; if (d < 7) return `${Math.floor(d)}d ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
const symbolsOf = it => (it.symbol ? [it.symbol] : (it.matched_symbols || []));
const RATE_CLASS = { Buy: "positive", Sell: "caution", Hold: "watch" };
function callPhrase(c) {
  const r = c.rating;
  if (c.action === "upgrade") return r ? `upgrades to ${r}` : "raises the target";
  if (c.action === "downgrade") return r ? `downgrades to ${r}` : "cuts the target";
  if (c.action === "initiate") return r ? `starts coverage with ${r}` : "starts coverage";
  if (c.action === "maintain") return r ? `maintains ${r}` : "maintains its view";
  return r ? `rates it ${r}` : "has a view";
}
function callHTML(c) {
  const url = safeUrl(c.url), co = state.names[c.symbol] || "";
  const tgt = c.target ? ` with a target of \u20b9${Number(c.target).toLocaleString("en-IN")}` : "";
  return `<article class="card call ${RATE_CLASS[c.rating] || "neutral"}" style="--s:10">
  <div class="candle" aria-hidden="true"><i></i></div>
  <div class="cbody">
    <div class="head"><div class="who"><span class="trust media">Reported by ${esc(c.source)}</span></div>${c.rating ? `<div class="sig"><b class="rate">${esc(c.rating)}</b></div>` : ""}</div>
    ${co ? `<div class="co">${esc(co)}</div>` : ""}
    <h2 class="title small">${esc(c.broker)} ${esc(callPhrase(c))}${tgt}</h2>
    <div class="chips"><button class="chip" data-sym="${esc(c.symbol)}" aria-pressed="${state.watch.includes(c.symbol)}" aria-label="Watch ${esc(c.symbol)}">${STAR}${esc(c.symbol)}</button></div>
    <div class="foot"><span>${ago(c.published_at)}</span>${url ? `<a class="go" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Read original</a>` : ""}</div>
  </div></article>`;
}
function cardHTML(it) {
  const sig = it.signal && it.signal !== "neutral" ? it.signal : "neutral";
  const syms = [...new Set(symbolsOf(it))];
  const co = it.company || (syms.length < 3 && syms[0] && state.names[syms[0]]) || "";
  const official = it.kind === "official";
  const text = it.summary || it.body || "";
  const ai = it.summary_source === "gemini" || it.summary_source === "groq";
  const url = safeUrl(it.url);
  return `<article class="card ${sig}" style="--s:${Number(it.score) || 0}">
  <div class="candle" aria-hidden="true"><i></i></div>
  <div class="cbody">
    <div class="head">
      <div class="who"><span class="trust ${official ? "official" : "media"}">${official ? CHECK : ""}${official ? "Official" : "Media"}</span><span>${esc(it.source)}</span></div>
      ${sig !== "neutral" ? `<div class="sig" aria-label="${LABEL[sig]} signal, score ${it.score} of 10"><b>${it.score}<small>/10</small></b><span>${LABEL[sig]}</span></div>` : ""}
    </div>
    ${co ? `<div class="co">${esc(co)}</div>` : ""}
    <h2 class="title">${esc(it.title)}</h2>
    ${text ? `<p class="summary">${esc(text)}</p>` : ""}
    ${ai ? '<div class="ai">Summary written by AI from the original text</div>' : ""}
    ${it.reason ? `<div class="why"><b>Why flagged:</b> ${esc(it.reason)}</div>` : ""}
    ${syms.length ? `<div class="chips">${syms.map(s => `<button class="chip" data-sym="${esc(s)}" aria-pressed="${state.watch.includes(s)}" aria-label="Watch ${esc(s)}" title="${esc(state.names[s] || s)}">${STAR}${esc(s)}</button>`).join("")}</div>` : ""}
    <div class="foot"><span>${ago(it.published_at)}</span>${it.sources_count > 1 ? `<span class="corro">Reported by ${it.sources_count} sources</span>` : ""}${url ? `<a class="go" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Read original</a>` : ""}</div>
  </div></article>`;
}
const io = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
}), { root: feed, threshold: 0.35 }) : null;
const ioMore = "IntersectionObserver" in window ? new IntersectionObserver(es => {
  if (es.some(e => e.isIntersecting)) loadMore();
}, { root: feed, rootMargin: "0px 0px 600px 0px" }) : null;

function appendCards(rows) {
  const frag = document.createElement("div");
  frag.innerHTML = rows.map(state.tab === "calls" ? callHTML : cardHTML).join("");
  const cards = [...frag.children];
  cards.forEach(c => { feed.append(c); io ? io.observe(c) : c.classList.add("in"); });
  if (ioMore) { ioMore.disconnect(); const all = $$(".card", feed); const t = all[Math.max(0, all.length - 4)]; if (t) ioMore.observe(t); }
}
function showNote(title, text, btn) {
  feed.innerHTML = `<div class="note"><h2>${esc(title)}</h2><p>${esc(text)}</p>${btn ? `<button class="btn" data-act="${btn[1]}">${esc(btn[0])}</button>` : ""}</div>`;
}
function skeleton() { feed.innerHTML = '<div class="skel"></div><div class="skel"></div>'; }

async function loadPage(first) {
  if (state.loading || (state.done && !first)) return;
  if (state.tab === "watch" && !state.watch.length) { state.done = true; return showNote("Follow stocks to see their news", "Tap Add stock and search by company name or symbol. Your list is saved on this device.", ["Add stock", "add"]); }
  state.loading = true;
  const gen = state.gen;
  try {
    await Promise.race([state.ready, new Promise(r => setTimeout(r, 1500))]);
    let rows = await api(buildQuery());
    if (gen !== state.gen) return;
    if (state.f.sector !== "all" && state.tab !== "calls") {
      rows = rows.filter(it => symbolsOf(it).some(s => state.sect[s] === state.f.sector));
      state.done = true;
    } else {
      state.offset += rows.length;
      if (rows.length < PAGE) state.done = true;
    }
    rows = rows.filter(r => !state.seen.has(r.external_id || r.call_id));
    rows.forEach(r => state.seen.add(r.external_id || r.call_id));
    if (first) feed.innerHTML = "";
    if (!rows.length && first) return showNote(...emptyCopy());
    appendCards(rows);
    state.loadedAt = Date.now();
  } catch (e) {
    if (gen !== state.gen) return;
    if (first) showNote("Could not load news", `${e.message}. Check your connection and the Supabase values in config.js.`, ["Try again", "retry"]);
  } finally { if (gen === state.gen) state.loading = false; }
}
const loadMore = () => loadPage(false);
function emptyCopy() {
  if (state.tab === "calls") return ["No broker calls found", "Calls appear when a publisher reports a rating or target price. Try All calls or check back later.", null];
  if (state.tab === "watch") return ["No news on your stocks yet", "Nothing matched your stocks in the stored news. New items appear here as they arrive.", null];
  if (state.tab === "opps") return ["No signals match these filters", "Lower the minimum score or widen the time range in Filters.", ["Open filters", "filters"]];
  return ["Nothing found", "Try a longer time range or fewer filters.", ["Open filters", "filters"]];
}
function reload() {
  state.gen++; state.items = []; state.seen = new Set(); state.offset = 0; state.done = false; state.loading = false;
  feed.classList.toggle("list", state.tab === "browse" || state.tab === "calls");
  feed.scrollTop = 0; skeleton(); loadPage(true);
  const d = JSON.stringify(state.f) !== JSON.stringify(DEFAULTS); $("#filter-dot").hidden = !d;
}
let rt; const reloadSoon = () => { clearTimeout(rt); rt = setTimeout(reload, 250); };

// ---------- watchlist (saved on this device; moves to your account after login) ----------
function toggleWatch(sym) {
  const i = state.watch.indexOf(sym);
  i >= 0 ? state.watch.splice(i, 1) : state.watch.push(sym);
  store.set("sp_watch", state.watch);
  $$(`[data-sym="${qa(sym)}"]`).forEach(b => b.setAttribute("aria-pressed", String(state.watch.includes(sym))));
  $$(`.star[data-star="${qa(sym)}"]`).forEach(b => b.setAttribute("aria-pressed", String(state.watch.includes(sym))));
  renderStrip(); syncPushSoon();
  if (state.tab === "watch" || (state.tab === "calls" && state.call.mine)) reloadSoon();
}
function renderStrip() {
  const s = $("#watch-strip");
  if (state.tab === "calls") {
    s.hidden = false;
    s.innerHTML = ["all", "Buy", "Hold", "Sell"].map(r => `<button class="pill sel" data-call="rating:${r}" aria-pressed="${state.call.rating === r}">${r === "all" ? "All calls" : r}</button>`).join("")
      + `<button class="pill sel" data-call="mine" aria-pressed="${state.call.mine}">My stocks</button>`;
    return;
  }
  s.hidden = state.tab !== "watch";
  s.innerHTML = state.watch.map(w => `<span class="pill">${esc(w)}<i role="button" tabindex="0" data-rm="${esc(w)}" aria-label="Remove ${esc(w)}">&times;</i></span>`).join("") + '<button class="pill add" data-act="add">Add stock</button>';
}

// ---------- alerts (web push), install, offline ----------
const VAPID = (window.CONFIG || {}).VAPID_PUBLIC_KEY;
const pushOK = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
const u8 = b64 => { const r = atob((b64 + "=".repeat((4 - b64.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from([...r].map(c => c.charCodeAt(0))); };
async function rpc(fn, args) {
  const r = await fetch(`${U}/rest/v1/rpc/${fn}`, { method: "POST", headers: { apikey: K, Authorization: `Bearer ${K}`, "Content-Type": "application/json" }, body: JSON.stringify(args) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}
const getSub = async () => pushOK ? (await navigator.serviceWorker.ready).pushManager.getSubscription() : null;
async function saveSub(sub) {
  const j = sub.toJSON();
  await rpc("save_push_sub", { p_endpoint: j.endpoint, p_p256dh: j.keys.p256dh, p_auth: j.keys.auth, p_symbols: state.watch, p_watch_min: state.alerts.watchMin, p_global_min: state.alerts.globalMin });
}
let ps; function syncPushSoon() { clearTimeout(ps); ps = setTimeout(async () => { try { const sub = await getSub(); if (sub) await saveSub(sub); } catch {} }, 1500); }
async function updateAlertsUI() {
  const st = $("#alerts-status"), b = $("#alerts-btn"); b.hidden = true;
  if (!VAPID) return void (st.textContent = "Alerts are not set up yet. Add VAPID_PUBLIC_KEY to config.js.");
  if (!pushOK) return void (st.textContent = /iPhone|iPad|iPod/.test(navigator.userAgent) ? "On iPhone, add this app to your Home Screen first, then open it from there." : "This browser does not support alerts.");
  if (Notification.permission === "denied") return void (st.textContent = "Notifications are blocked for this site. Allow them in your browser's site settings.");
  const sub = await getSub().catch(() => null);
  b.hidden = false; b.textContent = sub ? "Turn off alerts" : "Turn on alerts";
  st.textContent = sub ? "Alerts are on for this device." : "Alerts are off.";
}
$("#alerts-btn").onclick = async () => {
  const st = $("#alerts-status");
  try {
    const sub = await getSub();
    if (sub) { await rpc("delete_push_sub", { p_endpoint: sub.endpoint }); await sub.unsubscribe(); }
    else {
      if (await Notification.requestPermission() !== "granted") throw new Error("notifications were not allowed");
      const reg = await navigator.serviceWorker.ready;
      await saveSub(await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: u8(VAPID) }));
    }
  } catch (e) { st.textContent = `Could not change alerts: ${e.message}`; return; }
  updateAlertsUI();
};
let installEvt;
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); installEvt = e; $("#install").hidden = false; });
window.addEventListener("appinstalled", () => { $("#install").hidden = true; });
$("#install").onclick = async () => { if (installEvt) { installEvt.prompt(); await installEvt.userChoice; installEvt = null; $("#install").hidden = true; } };
const setOffline = () => { $("#offline").hidden = navigator.onLine !== false; };
window.addEventListener("online", () => { setOffline(); reload(); }); window.addEventListener("offline", setOffline); setOffline();
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));

// ---------- tabs, sheet, search, theme ----------
function setTab(t) {
  if (t === state.tab) { feed.scrollTo?.({ top: 0 }); return reload(); }
  state.tab = t;
  $$(".nav button").forEach(b => { if (b.dataset.tab === t) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  renderStrip(); reload();
}
function syncSheet() {
  $$("[data-f]").forEach(g => $$("button", g).forEach(b => b.setAttribute("aria-pressed", String(String(state.f[g.dataset.f]) === b.dataset.v))));
  $$("[data-a]").forEach(g => $$("button", g).forEach(b => b.setAttribute("aria-pressed", String(String(state.alerts[g.dataset.a]) === b.dataset.v))));
  updateAlertsUI();
  $("#minScore").value = state.f.minScore; $("#minScoreVal").textContent = state.f.minScore;
}
let lastFocus;
function openLayer(el, withScrim) { lastFocus = document.activeElement; el.hidden = false; $("#scrim").hidden = !withScrim; }
function closeLayers() {
  ["#sheet", "#search", "#scrim"].forEach(s => { $(s).hidden = true; });
  if (lastFocus?.focus) lastFocus.focus();
}
function openSearch(mode) {
  openLayer($("#search"), false); const q = $("#q");
  q.dataset.mode = mode; q.value = ""; q.placeholder = mode === "add" ? "Add a stock by name or symbol" : "Search stocks and news";
  runSearch(); q.focus();
}
let st;
function runSearch() {
  const q = $("#q").value.trim(), mode = $("#q").dataset.mode, out = $("#search-out"), up = q.toUpperCase(), lo = q.toLowerCase();
  let stocks = q ? state.companies.filter(c => c.symbol.startsWith(up) || c.symbol.includes(up) || c.name.toLowerCase().includes(lo)).slice(0, 8)
                 : state.watch.map(s => ({ symbol: s, name: state.names[s] || "" }));
  const row = c => `<div class="row"><div class="t"><b>${esc(c.symbol)}</b><small>${esc(c.name)}${state.sect[c.symbol] ? " in " + esc(state.sect[c.symbol]) : ""}</small></div>
    <button class="star" data-star="${esc(c.symbol)}" aria-pressed="${state.watch.includes(c.symbol)}" aria-label="Watch ${esc(c.symbol)}">${STAR}</button></div>`;
  out.innerHTML = (stocks.length ? `<h3>${q ? "Stocks" : "Your stocks"}</h3>` + stocks.map(row).join("") : (q ? '<h3>No stock matches</h3>' : '<h3>Type a company name or symbol</h3>'))
    + '<div id="news-res"></div>';
  clearTimeout(st);
  if (mode !== "add" && q.length >= 2) st = setTimeout(async () => {
    const safe = q.replace(/[,()*%&:"'\\]/g, " ").trim(); if (!safe) return;
    try {
      const rows = await api(`items?select=${FIELDS}&or=(title.ilike.*${encodeURIComponent(safe)}*,company.ilike.*${encodeURIComponent(safe)}*,symbol.ilike.*${encodeURIComponent(safe)}*)&order=published_at.desc.nullslast&limit=20`);
      if ($("#q").value.trim() !== q) return;
      $("#news-res").innerHTML = rows.length ? "<h3>News</h3>" + rows.map(r => {
        const u = safeUrl(r.url), s = r.signal && r.signal !== "neutral" ? r.signal : "";
        return `<${u ? `a href="${esc(u)}" target="_blank" rel="noopener noreferrer"` : "div"} class="row"><div class="t">${esc(r.title)}<small>${esc(r.source)}, ${ago(r.published_at)}</small></div>${s ? `<span class="s ${s}">${LABEL[s]} ${r.score}</span>` : ""}</${u ? "a" : "div"}>`;
      }).join("") : "<h3>No news found</h3>";
    } catch (e) { $("#news-res").innerHTML = `<h3>Search failed: ${esc(e.message)}</h3>`; }
  }, 300);
}
function applyTheme() {
  const t = state.theme, root = document.documentElement;
  t === "auto" ? root.removeAttribute("data-theme") : root.setAttribute("data-theme", t);
  const dark = t === "dark" || (t === "auto" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
  $('meta[name="theme-color"]').setAttribute("content", dark ? "#0E1422" : "#EDF0F6");
  $("#btn-theme").setAttribute("aria-label", `Theme: ${t}. Tap to change`);
}

// ---------- events ----------
document.addEventListener("click", e => {
  const t = e.target.closest("button, [data-rm], [data-act]"); if (!t) return;
  if (t.dataset.sym) return toggleWatch(t.dataset.sym);
  if (t.dataset.star) return toggleWatch(t.dataset.star);
  if (t.dataset.rm) return toggleWatch(t.dataset.rm);
  if (t.dataset.tab) return setTab(t.dataset.tab);
  if (t.dataset.call) {
    if (t.dataset.call === "mine") state.call.mine = !state.call.mine; else state.call.rating = t.dataset.call.split(":")[1];
    store.set("sp_call", state.call); renderStrip(); return reloadSoon();
  }
  const ga = t.closest("[data-a]");
  if (ga && t.dataset.v !== undefined) { state.alerts[ga.dataset.a] = Number(t.dataset.v); store.set("sp_alerts", state.alerts); syncSheet(); return syncPushSoon(); }
  const act = t.dataset.act;
  if (act === "add") return openSearch("add");
  if (act === "retry") return reload();
  if (act === "filters") { syncSheet(); return openLayer($("#sheet"), true); }
  const g = t.closest("[data-f]");
  if (g && t.dataset.v !== undefined) {
    const k = g.dataset.f; state.f[k] = k === "days" ? Number(t.dataset.v) : t.dataset.v;
    store.set("sp_filters", state.f); syncSheet(); reloadSoon();
  }
});
$("#btn-search").onclick = () => openSearch("all");
$("#btn-filter").onclick = () => { syncSheet(); openLayer($("#sheet"), true); };
$("#sheet-close").onclick = $("#search-close").onclick = closeLayers;
$("#scrim").onclick = closeLayers;
$("#reset").onclick = () => { state.f = { ...DEFAULTS }; store.set("sp_filters", state.f); syncSheet(); reloadSoon(); };
$("#minScore").oninput = e => { state.f.minScore = Number(e.target.value); $("#minScoreVal").textContent = state.f.minScore; store.set("sp_filters", state.f); reloadSoon(); };
$("#q").oninput = () => { clearTimeout(window._qt); window._qt = setTimeout(runSearch, 150); };
$("#btn-theme").onclick = () => { state.theme = { auto: "light", light: "dark", dark: "auto" }[state.theme]; store.set("sp_theme", state.theme); applyTheme(); };
document.addEventListener("keydown", e => {
  if (e.key === "Escape") return closeLayers();
  if ((e.key === "Enter" || e.key === " ") && e.target.dataset?.rm) { e.preventDefault(); return toggleWatch(e.target.dataset.rm); }
  if (/INPUT|TEXTAREA/.test(document.activeElement.tagName) || e.metaKey || e.ctrlKey) return;
  if (["ArrowDown", "j", "PageDown"].includes(e.key) || ["ArrowUp", "k", "PageUp"].includes(e.key)) {
    const dir = ["ArrowDown", "j", "PageDown"].includes(e.key) ? 1 : -1;
    if (state.tab !== "browse") { e.preventDefault(); feed.scrollBy?.({ top: dir * feed.clientHeight, behavior: reduceMotion ? "auto" : "smooth" }); }
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - state.loadedAt > 5 * 60e3 && $("#sheet").hidden && $("#search").hidden) reload();
});

// ---------- init ----------
$("#sector-chips").innerHTML = ["all", ...SECTORS].map(s => `<button data-v="${esc(s)}">${s === "all" ? "All sectors" : esc(s)}</button>`).join("");
applyTheme(); syncSheet(); renderStrip();
if (!U || U.includes("YOUR-PROJECT")) showNote("Add your Supabase details", "Open web/config.js and paste your project URL and anon key.");
else { state.ready = loadCompanies().catch(() => {}); reload(); }
})();
