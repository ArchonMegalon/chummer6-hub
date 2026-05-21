const CACHE_NAME = "chummer-public-v2";
const SHELL_CACHE = `${CACHE_NAME}-shell`;
const RUNTIME_CACHE = `${CACHE_NAME}-runtime`;
const NAVIGATION_FALLBACK = "/mobile";
const PRECACHE_URLS = [
  "/",
  "/mobile",
  "/play",
  "/play/continuity",
  "/packages",
  "/downloads",
  "/help",
  "/status",
  "/manifest.webmanifest",
  "/manifest.json",
  "/css/site.css",
  "/js/site.js",
  "/mobile/pwa.json",
  "/ready/handoff/mobile.json",
  "/pwa-icon.svg",
  "/pwa-maskable.svg",
  "/pwa-screenshot-mobile.svg",
  "/pwa-screenshot-wide.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== SHELL_CACHE && key !== RUNTIME_CACHE).map((key) => caches.delete(key))))
      .then(async () => {
        if ("navigationPreload" in self.registration) {
          await self.registration.navigationPreload.enable();
        }

        return self.clients.claim();
      })
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const requestUrl = new URL(event.request.url);
  if (requestUrl.origin !== self.location.origin) {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const preload = await event.preloadResponse;
          if (preload) {
            return preload;
          }

          const response = await fetch(event.request);
          const copy = response.clone();
          event.waitUntil(
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(event.request, copy))
          );
          return response;
        } catch {
          const cachedRoute = await caches.match(event.request);
          if (cachedRoute) {
            return cachedRoute;
          }

          const mobileRail = await caches.match(NAVIGATION_FALLBACK);
          if (mobileRail) {
            return mobileRail;
          }

          const landingRail = await caches.match("/");
          if (landingRail) {
            return landingRail;
          }

          return Response.error();
        }
      })()
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cached = await caches.match(event.request);
      const isStaticAsset = ["/css/", "/js/", ".svg", ".json"].some((segment) => requestUrl.pathname.includes(segment));
      if (cached && isStaticAsset) {
        event.waitUntil(refreshRuntime(event.request));
        return cached;
      }

      if (cached) {
        return cached;
      }

      try {
        return await refreshRuntime(event.request);
      } catch {
        return cached || Response.error();
      }
    })()
  );
});

async function refreshRuntime(request) {
  const response = await fetch(request);
  if (!response.ok) {
    return response;
  }

  const copy = response.clone();
  await caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
  return response;
}
