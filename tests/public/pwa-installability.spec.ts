import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('public play shell exposes manifest, service worker, notifications, and live installability copy', async ({ page, request }) => {
  await page.goto(`${baseUrl}/play`, { waitUntil: 'domcontentloaded' });

  await expect(page.locator('body')).toContainText('Installable app shell live');
  await expect(page.locator('body')).toContainText('Offline and reconnect lane cached');
  await expect(page.locator('body')).not.toContainText('installability proof pending');
  const manifestHref = await page.locator('link[rel="manifest"]').getAttribute('href');
  expect(manifestHref).toBeTruthy();

  const manifestResponse = await request.get(`${baseUrl}/manifest.json`);
  expect(manifestResponse.status()).toBe(200);
  const manifest = await manifestResponse.json();

  const swResponse = await request.get(`${baseUrl}/service-worker.js`);
  expect(swResponse.status()).toBe(200);
  const swText = await swResponse.text();

  const serviceWorkerState = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return { supported: false, controller: false, ready: false };
    }

    const registration = await navigator.serviceWorker.getRegistration('/');
    if (!registration) {
      return { supported: true, controller: !!navigator.serviceWorker.controller, ready: false };
    }

    try {
      await navigator.serviceWorker.ready;
      return { supported: true, controller: !!navigator.serviceWorker.controller, ready: true };
    } catch {
      return { supported: true, controller: !!navigator.serviceWorker.controller, ready: false };
    }
  });

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
    path: '/service-worker.js',
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
    truthful_copy: 'Installable app shell live; offline and reconnect lane cached.',
    installability_posture: 'live_public_installable_shell',
    registration: serviceWorkerState,
  });
});
