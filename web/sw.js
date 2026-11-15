const SHELL = "sp-shell-v6", DATA = "sp-data";
const FILES = ["./", "index.html", "styles.css", "app.js", "config.js", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL && k !== DATA && k !== "sp-fonts").map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

async function networkFirst(req, cacheName, timeoutMs, keep) {
  const cache = await caches.open(cacheName);
  try {
    const res = await Promise.race([fetch(req), new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), timeoutMs))]);
    if (res.ok) {
      await cache.put(req, res.clone());
      if (keep) { const ks = await cache.keys(); for (const k of ks.slice(0, Math.max(0, ks.length - keep))) await cache.delete(k); }
    }
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreVary: true });
    if (hit) return hit;
    return new Response(JSON.stringify({ error: "offline" }), { status: 503, headers: { "Content-Type": "application/json" } });
  }
}
async function staleWhileRevalidate(req) {
  const cache = await caches.open("sp-fonts"), hit = await cache.match(req);
  const net = fetch(req).then(r => { if (r.ok) cache.put(req, r.clone()); return r; }).catch(() => hit);
  return hit || net;
}
self.addEventListener("fetch", e => {
  const r = e.request; if (r.method !== "GET") return;
  const u = new URL(r.url);
  if (u.pathname.includes("/rest/v1/") && u.hostname.endsWith(".supabase.co")) return e.respondWith(networkFirst(r, DATA, 8000, 60));
  if (u.origin === location.origin) return e.respondWith(networkFirst(r, SHELL, 5000, 0));
  if (/^fonts\.(googleapis|gstatic)\.com$/.test(u.hostname)) return e.respondWith(staleWhileRevalidate(r));
});

self.addEventListener("push", e => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "StockPulse", {
    body: d.body || "", tag: d.tag, icon: "icons/icon-192.png", badge: "icons/badge-96.png", data: { url: d.url || "./" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "./";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => {
    for (const c of cs) if ("focus" in c) return c.focus();
    return self.clients.openWindow(url);
  }));
});
