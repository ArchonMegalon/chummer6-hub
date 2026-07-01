const CACHE_NAME = "chummer-public-v4";
const SHELL_CACHE = `${CACHE_NAME}-shell`;
const RUNTIME_CACHE = `${CACHE_NAME}-runtime`;
const NAVIGATION_FALLBACK = "/mobile";
const NOTIFICATION_ICON = "/apple-touch-icon.png";
const NOTIFICATION_BADGE = "/favicon.ico";
const DEFAULT_NOTIFICATION_TITLE = "Chummer update";
const DEFAULT_NOTIFICATION_BODY = "Open Chummer to review the latest activity.";
const DEFAULT_NOTIFICATION_HREF = "/account/ledger/notifications";
const NOTIFICATION_ROUTE_PATHS = new Set([
  "/account/ledger/notifications",
  "/mobile",
  "/play",
  "/play/continuity",
  "/account",
  "/account/ledger",
  "/account/ledger/advisory",
  "/account/ledger/worldtick/validation",
  "/account/ledger/onboarding",
  "/account/passport",
  "/account/passport/open",
  "/ledger",
  "/ledger/map",
  "/ledger/newsroom",
  "/passport",
  "/passport/identity-network"
]);
const NOTIFICATION_ROUTE_PREFIXES = [
  "/account/ledger/factions/",
  "/ledger/turns/",
  "/ledger/newsroom/",
  "/passport/receipts/",
  "/passport/"
];
const NOTIFICATION_ASSET_PATHS = new Set([
  "/apple-touch-icon.png",
  "/favicon.ico",
  "/favicon.svg",
  "/pwa-icon.svg",
  "/pwa-maskable.svg"
]);
const NOTIFICATION_ASSET_PREFIXES = [
  "/images/",
  "/media/ledger/",
  "/media/promo/"
];
const NOTIFICATION_ASSET_SUFFIXES = [
  ".ico",
  ".jpg",
  ".jpeg",
  ".png",
  ".svg",
  ".webp"
];
const PRECACHE_URLS = [
  "/",
  "/mobile",
  "/mobile/player",
  "/mobile/gm",
  "/mobile/observer",
  "/play",
  "/play/continuity",
  "/packages",
  "/downloads",
  "/help",
  "/status",
  "/manifest.webmanifest",
  "/site.webmanifest",
  "/manifest.json",
  "/manifest.player.webmanifest",
  "/manifest.gm.webmanifest",
  "/css/site.css",
  "/js/site.js",
  "/mobile/pwa.json",
  "/ready/handoff/mobile.json",
  "/apple-touch-icon.png",
  "/favicon.ico",
  "/favicon.svg",
  "/pwa-icon.svg",
  "/pwa-maskable.svg",
  "/pwa-screenshot-mobile.svg",
  "/pwa-screenshot-wide.svg"
];
const PUBLIC_NAVIGATION_CACHE_PATHS = new Set([
  "/",
  "/mobile",
  "/mobile/player",
  "/mobile/gm",
  "/mobile/observer",
  "/play",
  "/play/continuity",
  "/packages",
  "/downloads",
  "/help",
  "/status"
]);
const PUBLIC_RUNTIME_CACHE_PREFIXES = [
  "/css/",
  "/js/",
  "/images/",
  "/media/",
  "/fonts/"
];
const PUBLIC_RUNTIME_CACHE_SUFFIXES = [
  ".css",
  ".js",
  ".svg",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".gif",
  ".ico",
  ".woff",
  ".woff2",
  ".ttf",
  ".eot",
  ".webmanifest",
  ".json",
  ".txt"
];
const NON_CACHEABLE_PATHS = new Set([
  "/mobile/pwa/ledger.json"
]);
const NON_CACHEABLE_PATH_PREFIXES = [
  "/account",
  "/api",
  "/admin",
  "/support",
  "/signin",
  "/signout",
  "/auth"
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
          if (shouldCacheResponse(event.request, response)) {
            const copy = response.clone();
            event.waitUntil(
              caches.open(RUNTIME_CACHE).then((cache) => cache.put(event.request, copy))
            );
          }
          return response;
        } catch {
          if (isPublicRuntimeCacheableRequest(event.request)) {
            const cachedRoute = await caches.match(event.request);
            if (cachedRoute) {
              return cachedRoute;
            }
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
      const cacheable = isPublicRuntimeCacheableRequest(event.request);
      const cached = cacheable ? await caches.match(event.request) : null;
      const isStaticAsset = PUBLIC_RUNTIME_CACHE_PREFIXES.some((prefix) => requestUrl.pathname.startsWith(prefix))
        || PUBLIC_RUNTIME_CACHE_SUFFIXES.some((suffix) => requestUrl.pathname.endsWith(suffix));
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

self.addEventListener("push", (event) => {
  event.waitUntil(handlePush(event));
});

self.addEventListener("notificationclick", (event) => {
  event.waitUntil(handleNotificationClick(event));
});

self.addEventListener("notificationclose", (event) => {
  event.waitUntil(handleNotificationClose(event));
});

async function refreshRuntime(request) {
  const response = await fetch(request);
  if (!shouldCacheResponse(request, response)) {
    return response;
  }

  const copy = response.clone();
  await caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
  return response;
}

function isPublicRuntimeCacheableRequest(request) {
  if (!request) {
    return false;
  }

  try {
    const url = new URL(request.url, self.location.origin);
    if (url.origin !== self.location.origin) {
      return false;
    }

    if (NON_CACHEABLE_PATHS.has(url.pathname)) {
      return false;
    }

    if (NON_CACHEABLE_PATH_PREFIXES.some((prefix) => url.pathname === prefix || url.pathname.startsWith(`${prefix}/`))) {
      return false;
    }

    if (request.mode === "navigate") {
      return PUBLIC_NAVIGATION_CACHE_PATHS.has(url.pathname);
    }

    if (PRECACHE_URLS.includes(url.pathname)) {
      return true;
    }

    return PUBLIC_RUNTIME_CACHE_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))
      || PUBLIC_RUNTIME_CACHE_SUFFIXES.some((suffix) => url.pathname.endsWith(suffix));
  } catch {
    return false;
  }
}

function shouldCacheResponse(request, response) {
  if (!response || !response.ok || response.status !== 200) {
    return false;
  }

  const cacheControl = response.headers.get("Cache-Control") || "";
  if (cacheControl.toLowerCase().includes("no-store") || cacheControl.toLowerCase().includes("private")) {
    return false;
  }

  return isPublicRuntimeCacheableRequest(request);
}
async function handlePush(event) {
  const payload = normalizePushPayload(event);
  const href = normalizeNotificationHref(payload.href || payload.route || payload.url || DEFAULT_NOTIFICATION_HREF);
  const actionRoutes = {};
  const notificationData = {
    href,
    route: href,
    tag: payload.tag || "chummer-update",
    family: payload.family || "general",
    notificationId: payload.notificationId || payload.id || null,
    receivedAt: new Date().toISOString(),
    source: "service-worker-push"
  };

  await broadcastClientMessage("chummer:pwa-notification-push", {
    title: payload.title || DEFAULT_NOTIFICATION_TITLE,
    body: payload.body || DEFAULT_NOTIFICATION_BODY,
    data: notificationData
  });

  if (payload.silent === true) {
    return;
  }

  const options = {
    body: payload.body || DEFAULT_NOTIFICATION_BODY,
    icon: normalizeNotificationAssetPath(payload.icon, NOTIFICATION_ICON),
    badge: normalizeNotificationAssetPath(payload.badge, NOTIFICATION_BADGE),
    tag: notificationData.tag,
    data: notificationData,
    renotify: payload.renotify === true,
    requireInteraction: payload.requireInteraction === true,
    silent: false
  };

  if (Array.isArray(payload.actions) && payload.actions.length > 0) {
    options.actions = payload.actions
      .map((action) => {
        if (!action || !action.action || !action.title) {
          return null;
        }

        const actionId = String(action.action).trim();
        const actionTitle = String(action.title).trim();
        const actionHref = tryNormalizeNotificationHref(action.href || action.route || action.url || "");
        if (!actionId || !actionTitle) {
          return null;
        }
        if (!actionHref) {
          return null;
        }

        actionRoutes[actionId] = actionHref;
        return {
          action: actionId,
          title: actionTitle
        };
      })
      .filter(Boolean)
      .slice(0, 2);
  }

  if (Object.keys(actionRoutes).length > 0) {
    notificationData.actionRoutes = actionRoutes;
  }

  await self.registration.showNotification(payload.title || DEFAULT_NOTIFICATION_TITLE, options);
}

async function handleNotificationClick(event) {
  const notification = event.notification;
  if (notification) {
    notification.close();
  }

  const href = resolveNotificationActionHref(event.action, notification?.data);

  await broadcastClientMessage("chummer:pwa-notification-click", {
    action: event.action || null,
    href,
    data: notification?.data || null
  });

  const windowClients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  const targetUrl = new URL(href, self.location.origin).href;

  for (const client of windowClients) {
    if (!("focus" in client)) {
      continue;
    }

    try {
      const clientUrl = new URL(client.url, self.location.origin);
      if (clientUrl.origin === self.location.origin) {
        await client.focus();
        if ("navigate" in client && client.url !== targetUrl) {
          await client.navigate(targetUrl);
        }
        return;
      }
    } catch {
      // Ignore malformed client URLs and continue trying.
    }
  }

  if (self.clients.openWindow) {
    await self.clients.openWindow(targetUrl);
  }
}

async function handleNotificationClose(event) {
  await broadcastClientMessage("chummer:pwa-notification-close", {
    href: normalizeNotificationHref(event.notification?.data?.href || event.notification?.data?.route || DEFAULT_NOTIFICATION_HREF),
    data: event.notification?.data || null
  });
}

function normalizePushPayload(event) {
  if (!event || !event.data) {
    return {};
  }

  try {
    const json = event.data.json();
    return json && typeof json === "object" ? json : {};
  } catch {
    try {
      const text = event.data.text();
      if (!text) {
        return {};
      }

      return {
        title: DEFAULT_NOTIFICATION_TITLE,
        body: text
      };
    } catch {
      return {};
    }
  }
}

function normalizeNotificationHref(value) {
  return tryNormalizeNotificationHref(value) || DEFAULT_NOTIFICATION_HREF;
}

function tryNormalizeNotificationHref(value) {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(String(value), self.location.origin);
    if (url.origin !== self.location.origin) {
      return null;
    }

    if (!isAllowedNotificationHref(url.pathname)) {
      return null;
    }

    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

function normalizeNotificationAssetPath(value, fallback) {
  return tryNormalizeNotificationAssetPath(value) || fallback;
}

function tryNormalizeNotificationAssetPath(value) {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(String(value), self.location.origin);
    if (url.origin !== self.location.origin) {
      return null;
    }

    if (!isAllowedNotificationAssetPath(url.pathname)) {
      return null;
    }

    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

function isAllowedNotificationHref(pathname) {
  return NOTIFICATION_ROUTE_PATHS.has(pathname)
    || NOTIFICATION_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isAllowedNotificationAssetPath(pathname) {
  const lowerPath = String(pathname || "").toLowerCase();
  const hasAllowedExtension = NOTIFICATION_ASSET_SUFFIXES.some((suffix) => lowerPath.endsWith(suffix));
  if (!hasAllowedExtension) {
    return false;
  }

  return NOTIFICATION_ASSET_PATHS.has(pathname)
    || NOTIFICATION_ASSET_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function resolveNotificationActionHref(actionId, data) {
  const actionRoutes = data?.actionRoutes;
  if (actionId && actionRoutes && typeof actionRoutes === "object") {
    const routed = actionRoutes[String(actionId)];
    if (routed) {
      return normalizeNotificationHref(routed);
    }
  }

  return normalizeNotificationHref(
    data?.href
      || data?.route
      || DEFAULT_NOTIFICATION_HREF
  );
}

async function broadcastClientMessage(type, payload) {
  const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  await Promise.all(
    clients.map(async (client) => {
      try {
        client.postMessage({ type, payload });
      } catch {
        // Ignore postMessage failures for detached or unavailable clients.
      }
    })
  );
}
