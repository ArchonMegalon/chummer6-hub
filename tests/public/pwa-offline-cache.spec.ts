import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('service worker caches the public shell strongly enough for offline mobile replay fallback', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'domcontentloaded' });

  await page.evaluate(async () => {
    if ('serviceWorker' in navigator) {
      await navigator.serviceWorker.ready;
    }
  });

  const cacheSnapshot = await page.evaluate(async () => {
    if (!('caches' in window)) {
      return { supported: false, entries: [] as Array<{ cacheName: string; url: string; pathname: string }> };
    }

    const entries: Array<{ cacheName: string; url: string; pathname: string }> = [];
    for (const cacheName of await caches.keys()) {
      const cache = await caches.open(cacheName);
      for (const request of await cache.keys()) {
        const parsed = new URL(request.url);
        entries.push({ cacheName, url: request.url, pathname: parsed.pathname });
      }
    }

    return { supported: true, entries };
  });
  expect(cacheSnapshot.supported).toBeTruthy();
  const cachedPaths = new Set(cacheSnapshot.entries.map((entry) => entry.pathname));
  for (const expectedPath of ['/mobile', '/play', '/play/continuity', '/mobile/pwa.json', '/ready/handoff/mobile.json']) {
    expect(cachedPaths.has(expectedPath), `${expectedPath} should be present in Cache Storage`).toBeTruthy();
  }
  expect(cachedPaths.has('/mobile/pwa/ledger.json'), 'personalized ledger stream must not be cached').toBeFalsy();

  await context.setOffline(true);
  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText('Installable app shell live');
  await expect(page.locator('body')).toContainText('Offline and reconnect lane cached');
  await expect(page.locator('body')).not.toContainText('installability proof pending');

  writeJsonArtifact('PWA_OFFLINE_CACHE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/mobile',
    offline_reload: 'pass',
    cached_paths: [...cachedPaths].sort(),
    personalized_ledger_cached: cachedPaths.has('/mobile/pwa/ledger.json'),
  });
});
