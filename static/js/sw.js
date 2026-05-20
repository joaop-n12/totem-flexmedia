/* Service Worker do Totem FlexMedia
 * Estrategia:
 *   - Navegacoes (paginas HTML): network-first com fallback para /offline
 *   - Estaticos (CSS, JS, imagens, fontes): cache-first (stale-while-revalidate)
 *   - Chamadas de API (/api/*): sempre rede; se falhar, devolve JSON com flag offline
 *
 * Incrementar CACHE_VERSION a cada deploy para invalidar o cache antigo.
 */

const CACHE_VERSION = "totem-v3";
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const PAGES_CACHE   = `${CACHE_VERSION}-pages`;

const PRECACHE_URLS = [
  "/offline",
  "/static/css/style.css",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  // Remove caches de versoes antigas
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => !k.startsWith(CACHE_VERSION)).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Utilitario: verifica se a requisicao e para um asset estatico cacheavel
function isStaticAsset(url) {
  return url.pathname.startsWith("/static/") ||
         url.hostname.endsWith("gstatic.com") ||
         url.hostname.endsWith("googleapis.com");
}

function emptyStaticResponse(req) {
  const accept = req.headers.get("accept") || "";
  const contentType = accept.includes("text/css") ? "text/css" : "text/plain";
  return new Response("", { status: 504, headers: { "Content-Type": contentType } });
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // APIs: nunca cachear. Se falhar, devolver JSON amigavel.
  if (url.pathname.includes("/api/")) {
    event.respondWith(
      fetch(req).catch(() =>
        new Response(
          JSON.stringify({
            error: "offline",
            message: "Sem conexao com a internet. Tente novamente em alguns instantes."
          }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    return;
  }

  // Navegacao (paginas HTML): network-first, fallback cache, fallback /offline
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(PAGES_CACHE).then((c) => c.put(req, copy));
          return resp;
        })
        .catch(() =>
          caches.match(req).then((cached) => cached || caches.match("/offline"))
        )
    );
    return;
  }

  // Estaticos: stale-while-revalidate
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.match(req).then((cached) => {
          const fetchPromise = fetch(req)
            .then((resp) => {
              if (resp && resp.status === 200) cache.put(req, resp.clone());
              return resp;
            })
            .catch(() => cached || emptyStaticResponse(req));
          return cached || fetchPromise;
        })
      )
    );
  }
});
