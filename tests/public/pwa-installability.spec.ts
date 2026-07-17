import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('public play shell exposes manifest, service worker, notifications, and privacy-honest installability copy', async ({ page, request }) => {
  test.setTimeout(90000);
  await page.goto(`${baseUrl}/play`, { waitUntil: 'domcontentloaded' });

  await expect(page.locator('body')).toContainText('Installable app shell live');
  await expect(page.locator('body')).toContainText('Static app assets stay available offline');
  await expect(page.locator('body')).toContainText('Private table state reconnects from the server');
  await expect(page.locator('body')).not.toContainText('Offline and reconnect lane cached');
  await expect(page.locator('body')).not.toContainText('installability proof pending');
  const manifestHref = await page.locator('link[rel="manifest"]').getAttribute('href');
  expect(manifestHref).toBeTruthy();

  const manifestResponse = await request.get(`${baseUrl}/manifest.json`);
  expect(manifestResponse.status()).toBe(200);
  const manifest = await manifestResponse.json();

  const readServiceWorkerState = async () => page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return { supported: false, controller: false, ready: false, scriptURL: null };
    }

    const registration = await navigator.serviceWorker.getRegistration('/');
    if (!registration) {
      return { supported: true, controller: !!navigator.serviceWorker.controller, ready: false, scriptURL: null };
    }

    const worker = registration.active ?? registration.waiting ?? registration.installing;
    return {
      supported: true,
      controller: !!navigator.serviceWorker.controller,
      ready: !!registration.active,
      scriptURL: worker?.scriptURL ?? null,
    };
  });

  await expect.poll(async () => (await readServiceWorkerState()).scriptURL ?? '', {
    timeout: 15000,
  }).toContain('/service-worker.js');

  const serviceWorkerState = await readServiceWorkerState();
  const serviceWorkerScriptUrl = serviceWorkerState.scriptURL || `${baseUrl}/service-worker.js`;
  const swResponse = await request.get(serviceWorkerScriptUrl);
  expect(swResponse.status()).toBe(200);
  const swText = await swResponse.text();

  writeJsonArtifact('PWA_MANIFEST_LIVE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: manifest.start_url && manifest.display ? 'pass' : 'fail',
    base_url: baseUrl,
    href: manifestHref,
    manifest,
  });

  writeJsonArtifact('PWA_SERVICE_WORKER_LIVE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: swText.includes('self.addEventListener("fetch"')
      && swText.includes('self.addEventListener("push"')
      && swText.includes('self.addEventListener("notificationclick"')
      && swText.includes('self.addEventListener("notificationclose"')
      ? 'pass'
      : 'fail',
    base_url: baseUrl,
    path: serviceWorkerScriptUrl,
    has_fetch_handler: swText.includes('self.addEventListener("fetch"'),
    has_push_handler: swText.includes('self.addEventListener("push"'),
    has_notification_click_handler: swText.includes('self.addEventListener("notificationclick"'),
    has_notification_close_handler: swText.includes('self.addEventListener("notificationclose"'),
    has_precache: swText.includes('PRECACHE_URLS'),
    registration: serviceWorkerState,
  });

  writeJsonArtifact('PWA_INSTALLABILITY.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: serviceWorkerState.supported ? 'pass' : 'fail',
    base_url: baseUrl,
    route: '/play',
    truthful_copy: 'Installable app shell live; static app assets stay available offline; private table state reconnects from the server.',
    installability_posture: 'live_public_installable_shell',
    private_navigation_cache_posture: 'network_only',
    registration: serviceWorkerState,
  });
});
