import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const legacyPrivateCachePrefixes = [
  'chummer-shell-play-shell-',
  'chummer-media-play-shell-',
  'chummer-media-meta-play-shell-',
];
const requiredStaticPaths = [
  '/mobile.css',
  '/mobile-install-shell.js',
  '/manifest.player.webmanifest',
  '/manifest.gm.webmanifest',
];
const unrelatedCacheName = 'chummer-build-static-proof-sentinel';
const v19StaticCacheNames = new Set([
  'chummer-public-root-static-run-api-projection-v2-v19',
  'chummer-mobile-play-static-run-api-projection-v2-v19',
]);

type CacheEntry = {
  cacheName: string;
  url: string;
  pathname: string;
  search: string;
  mode: string;
  cacheControl: string;
};

type CacheSnapshot = {
  supported: boolean;
  cacheNames: string[];
  entries: CacheEntry[];
};

test('v19 keeps private play navigation out of the exact public Cache Storage allowlist and fails closed offline', async ({ browser }) => {
  test.setTimeout(120000);
  const context = await browser.newContext();
  let page = await context.newPage();

  const readServiceWorkerState = async () => page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return { supported: false, controller: false, scriptURL: null };
    }

    const registration = await navigator.serviceWorker.getRegistration('/mobile/')
      ?? await navigator.serviceWorker.getRegistration('/');
    const worker = registration?.active ?? registration?.waiting ?? registration?.installing ?? null;
    return {
      supported: true,
      controller: !!navigator.serviceWorker.controller,
      scriptURL: worker?.scriptURL ?? null,
    };
  });

  const waitForV19Control = async () => {
    await expect.poll(async () => (await readServiceWorkerState()).scriptURL ?? '', {
      timeout: 30000,
    }).toContain('/service-worker.js');
    await page.evaluate(async () => {
      if ('serviceWorker' in navigator) {
        await navigator.serviceWorker.ready;
      }
    });
    if (!(await readServiceWorkerState()).controller) {
      await page.reload({ waitUntil: 'domcontentloaded' });
    }
    await expect.poll(async () => (await readServiceWorkerState()).controller, {
      timeout: 30000,
    }).toBeTruthy();
  };

  const readCacheSnapshot = async (): Promise<CacheSnapshot> => page.evaluate(async () => {
    if (!('caches' in window)) {
      return { supported: false, cacheNames: [], entries: [] };
    }

    const cacheNames = await caches.keys();
    const entries: CacheEntry[] = [];
    for (const cacheName of cacheNames) {
      const cache = await caches.open(cacheName);
      for (const request of await cache.keys()) {
        const parsed = new URL(request.url);
        if (parsed.origin !== window.location.origin) {
          continue;
        }
        const response = await cache.match(request);
        entries.push({
          cacheName,
          url: request.url,
          pathname: parsed.pathname,
          search: parsed.search,
          mode: request.mode,
          cacheControl: response?.headers.get('Cache-Control') ?? '',
        });
      }
    }

    return { supported: true, cacheNames, entries };
  });

  const publishWorkerNetworkState = async (online: boolean) => page.evaluate(async (nextOnline) => {
    const controller = 'serviceWorker' in navigator ? navigator.serviceWorker.controller : null;
    if (!controller) {
        throw new Error('mobile v19 service worker is not controlling the role page');
    }

    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        navigator.serviceWorker.removeEventListener('message', onMessage);
        reject(new Error('service worker did not acknowledge the network-state boundary'));
      }, 5000);
      const onMessage = (event: MessageEvent) => {
        const data = event.data ?? {};
        if (data.type !== 'chummer-play-network-state-ack' || data.online !== nextOnline) {
          return;
        }
        window.clearTimeout(timer);
        navigator.serviceWorker.removeEventListener('message', onMessage);
        resolve();
      };
      navigator.serviceWorker.addEventListener('message', onMessage);
      controller.postMessage({ type: 'chummer-play-network-state', online: nextOnline });
    });
  }, online);

  try {
    // `/mobile/` is the worker scope; use an in-scope role route so
    // `navigator.serviceWorker.ready` and controller assertions are meaningful.
    await page.goto(`${baseUrl}/mobile/player`, { waitUntil: 'domcontentloaded' });
    await waitForV19Control();
    await publishWorkerNetworkState(true);

    // Reinstall the worker over caches that model the private legacy namespaces.
    // Cache Storage survives unregister, so the next v19 activation must purge them.
    await page.evaluate(async ({ legacyPrefixes, unrelatedName }) => {
      const registrations = 'serviceWorker' in navigator
        ? await navigator.serviceWorker.getRegistrations()
        : [];
      await Promise.all(registrations.map((registration) => registration.unregister()));
      for (const prefix of legacyPrefixes) {
        const cache = await caches.open(`${prefix}v16`);
        await cache.put('/private-v16-marker', new Response('private projection'));
      }
      const unrelated = await caches.open(unrelatedName);
      await unrelated.put('/unrelated-cache-marker', new Response('preserve'));
    }, { legacyPrefixes: legacyPrivateCachePrefixes, unrelatedName: unrelatedCacheName });

    await page.close();
    page = await context.newPage();
    await page.goto(`${baseUrl}/mobile/player`, { waitUntil: 'domcontentloaded' });
    await waitForV19Control();
    await publishWorkerNetworkState(true);

    await expect.poll(async () => (await readCacheSnapshot()).cacheNames, {
      timeout: 30000,
    }).not.toEqual(expect.arrayContaining(legacyPrivateCachePrefixes.map((prefix) => `${prefix}v16`)));

    const roleRoutes = [
      { path: '/mobile/player', role: 'Player', installRole: 'player', manifest: '/manifest.player.webmanifest' },
      { path: '/mobile/gm', role: 'GameMaster', installRole: 'gm', manifest: '/manifest.gm.webmanifest' },
    ];
    for (const roleRoute of roleRoutes) {
      const rolePage = await context.newPage();
      const response = await rolePage.goto(`${baseUrl}${roleRoute.path}`, { waitUntil: 'domcontentloaded' });
      expect(response?.status()).toBe(200);
      const cacheControl = (await response?.headerValue('Cache-Control'))?.toLowerCase() ?? '';
      expect(cacheControl).toContain('private');
      expect(cacheControl).toContain('no-store');
      expect((await response?.headerValue('Referrer-Policy'))?.toLowerCase()).toBe('no-referrer');
      await expect(rolePage.locator(
        `[data-play-surface="install-only"][data-live-session="unavailable"][data-authority="none"][data-install-role="${roleRoute.installRole}"]`,
      ).first()).toBeVisible();
      await expect(rolePage.locator('link[rel="manifest"]').first()).toHaveAttribute('href', roleRoute.manifest);
      await expect(rolePage.locator('[data-turn-root]')).toHaveCount(0);
      await expect(rolePage.locator('[data-blazor-shell="interactive-server"]')).toHaveCount(0);
      await rolePage.close();
    }

    // Exercise query-bearing private navigation, then prove neither the query nor
    // the rendered role document entered Cache Storage.
    const privatePage = await context.newPage();
    const rejectedPrivateResponse = await privatePage.goto(
      `${baseUrl}/mobile/player?sessionId=private-proof&deviceId=private-device&role=Player`,
      { waitUntil: 'domcontentloaded' },
    );
    expect(rejectedPrivateResponse?.status()).toBe(404);
    expect((await rejectedPrivateResponse?.headerValue('Cache-Control'))?.toLowerCase()).toContain('no-store');
    expect((await rejectedPrivateResponse?.headerValue('Referrer-Policy'))?.toLowerCase()).toBe('no-referrer');
    await expect(privatePage.locator('[data-play-surface]')).toHaveCount(0);
    await expect(privatePage.locator('[data-turn-root]')).toHaveCount(0);
    await expect(privatePage.locator('[data-blazor-shell="interactive-server"]')).toHaveCount(0);
    await privatePage.close();

    const buildAssetResponse = await context.request.get(`${baseUrl}/blazor/app.css`);
    expect(buildAssetResponse.status()).toBe(200);

    const cacheSnapshot = await readCacheSnapshot();
    expect(cacheSnapshot.supported).toBeTruthy();
    expect(cacheSnapshot.cacheNames).toContain(unrelatedCacheName);
    const activeV19StaticCacheNames = cacheSnapshot.cacheNames.filter((name) => v19StaticCacheNames.has(name));
    expect(activeV19StaticCacheNames.length).toBeGreaterThan(0);
    expect(cacheSnapshot.cacheNames.some((name) => legacyPrivateCachePrefixes.some((prefix) => name.startsWith(prefix)))).toBeFalsy();

    const v19StaticEntries = cacheSnapshot.entries.filter((entry) => v19StaticCacheNames.has(entry.cacheName));
    const cachedPaths = new Set(v19StaticEntries.map((entry) => entry.pathname));
    for (const expectedPath of requiredStaticPaths) {
      expect(cachedPaths.has(expectedPath), `${expectedPath} should be available as a static shell asset`).toBeTruthy();
    }
    for (const entry of cacheSnapshot.entries) {
      expect(entry.search, `${entry.url} must not cache a query-bearing request`).toBe('');
      expect(entry.mode, `${entry.url} must not cache navigation`).not.toBe('navigate');
      expect(entry.pathname === '/mobile' || entry.pathname.startsWith('/mobile/'), `${entry.url} must not cache rendered mobile navigation`).toBeFalsy();
      expect(entry.pathname === '/play' || entry.pathname.startsWith('/play/'), `${entry.url} must not cache rendered play navigation`).toBeFalsy();
      expect(entry.pathname === '/blazor' || entry.pathname.startsWith('/blazor/'), `${entry.url} belongs to the Build PWA scope`).toBeFalsy();
      expect(entry.pathname === '/api' || entry.pathname.startsWith('/api/'), `${entry.url} must not cache API data`).toBeFalsy();
      expect(entry.pathname, `${entry.url} must not cache the personalized ledger`).not.toBe('/mobile/pwa/ledger.json');
      expect(entry.cacheControl.toLowerCase(), `${entry.url} must not cache a private response`).not.toContain('private');
      expect(entry.cacheControl.toLowerCase(), `${entry.url} must not cache a no-store response`).not.toContain('no-store');
    }

    const offlineRoleResults = [];
    for (const roleRoute of roleRoutes) {
      const offlineContext = await browser.newContext();
      try {
        const rolePage = await offlineContext.newPage();
        await rolePage.goto(`${baseUrl}${roleRoute.path}`, { waitUntil: 'domcontentloaded' });
        await rolePage.evaluate(async () => {
          if ('serviceWorker' in navigator) {
            await navigator.serviceWorker.ready;
          }
        });
        if (!await rolePage.evaluate(() => !!navigator.serviceWorker?.controller)) {
          await rolePage.reload({ waitUntil: 'domcontentloaded' });
        }
        expect(await rolePage.evaluate(() => !!navigator.serviceWorker?.controller)).toBeTruthy();
        await offlineContext.setOffline(true);
        const response = await rolePage.reload({ waitUntil: 'domcontentloaded' });
        expect(response?.status(), `${roleRoute.path} must fail closed offline`).toBe(503);
        expect((await response?.headerValue('Cache-Control'))?.toLowerCase()).toContain('no-store');
        expect((await response?.headerValue('Content-Security-Policy'))?.toLowerCase()).toContain("default-src 'none'");
        expect((await response?.headerValue('X-Content-Type-Options'))?.toLowerCase()).toBe('nosniff');
        await expect(rolePage.getByRole('heading', { name: "You're offline" })).toBeVisible();
        await expect(rolePage.getByText('No account or release data was loaded from an old page.')).toBeVisible();
        await expect(rolePage.locator('[data-turn-root]')).toHaveCount(0);
        await expect(rolePage.locator('#turn-companion-bootstrap')).toHaveCount(0);
        await expect(rolePage.locator('[data-blazor-shell="interactive-server"]')).toHaveCount(0);
        offlineRoleResults.push({
          role: roleRoute.role,
          path: roleRoute.path,
          status: response?.status(),
          cache_control: await response?.headerValue('Cache-Control'),
          private_projection_restored: false,
        });
      } finally {
        await offlineContext.setOffline(false).catch(() => undefined);
        await offlineContext.close();
      }
    }

    writeJsonArtifact('PWA_OFFLINE_CACHE.generated.json', {
      contractName: 'chummer.pwa_offline_cache.v2',
      generated_at_utc: new Date().toISOString(),
      status: 'pass',
      base_url: baseUrl,
      cache_version: 'v19',
      cache_contract: 'run-api-projection-v2',
      navigation_policy: 'network_only',
      private_state_scope: 'open_tab_only',
      query_bearing_requests_cached: false,
      private_navigation_cached: false,
      private_api_cached: false,
      build_scope_cached: false,
      personalized_ledger_cached: false,
      legacy_private_cache_prefixes_purged: legacyPrivateCachePrefixes,
      unrelated_cache_preserved: cacheSnapshot.cacheNames.includes(unrelatedCacheName),
      static_paths: [...cachedPaths].sort(),
      offline_role_fallbacks: offlineRoleResults,
    });
  } finally {
    await context.setOffline(false).catch(() => undefined);
    await context.close();
  }
});
