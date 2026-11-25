/* Network-only worker so a later Switch Survey update replaces a cached page. */
const VERSION = "2026-11-24l";
self.addEventListener("install", (event) => {
  self.skipWaiting();
});
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const accept = event.request.headers.get("accept") || "";
  if (event.request.mode === "navigate" || accept.includes("text/html") || /\/sw\.js/.test(event.request.url)) {
    event.respondWith(fetch(event.request, { cache: "no-store" }));
  }
});
