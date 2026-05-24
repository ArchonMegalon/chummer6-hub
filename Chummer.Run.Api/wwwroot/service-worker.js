const CACHE_NAME = "chummer-public-v2";
const SHELL_CACHE = `${CACHE_NAME}-shell`;
const RUNTIME_CACHE = `${CACHE_NAME}-runtime`;
const NAVIGATION_FALLBACK = "/mobile";
const NOTIFICATION_ICON = "/apple-touch-icon.png";
const NOTIFICATION_BADGE = "/favicon.ico";
const DEFAULT_NOTIFICATION_TITLE = "Chummer update";
const DEFAULT_NOTIFICATION_BODY = "Open Chummer to review the latest activity.";
const DEFAULT_NOTIFICATION_HREF = "/account/ledger/notifications";
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
  "/site.webmanifest",
  "/manifest.json",
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
  if (!response.ok) {
    return response;
  }

  const copy = response.clone();
  await caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
  return response;
}

async function handlePush(event) {
  const payload = normalizePushPayload(event);
  const href = normalizeNotificationHref(payload.href || payload.route || payload.url || DEFAULT_NOTIFICATION_HREF);
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
    icon: payload.icon || NOTIFICATION_ICON,
    badge: payload.badge || NOTIFICATION_BADGE,
    tag: notificationData.tag,
    data: notificationData,
    renotify: payload.renotify === true,
    requireInteraction: payload.requireInteraction === true,
    silent: false
  };

  if (Array.isArray(payload.actions) && payload.actions.length > 0) {
    options.actions = payload.actions
      .filter((action) => action && action.action && action.title)
      .slice(0, 2)
      .map((action) => ({
        action: String(action.action),
        title: String(action.title)
      }));
  }

  await self.registration.showNotification(payload.title || DEFAULT_NOTIFICATION_TITLE, options);
}

async function handleNotificationClick(event) {
  const notification = event.notification;
  if (notification) {
    notification.close();
  }

  const href = normalizeNotificationHref(
    event.action
      || notification?.data?.href
      || notification?.data?.route
      || DEFAULT_NOTIFICATION_HREF
  );

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
  if (!value) {
    return DEFAULT_NOTIFICATION_HREF;
  }

  try {
    const url = new URL(String(value), self.location.origin);
    if (url.origin !== self.location.origin) {
      return DEFAULT_NOTIFICATION_HREF;
    }

    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return DEFAULT_NOTIFICATION_HREF;
  }
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
