import { test, expect } from 'playwright/test';

const baseUrl = (process.env.CHUMMER_HUB_BASE_URL ?? 'http://127.0.0.1:8091').replace(/\/$/, '');

const routeExpectations: Array<{ route: string; finalPath: string }> = [
  { route: '/mobile', finalPath: '/mobile' },
  { route: '/pwa', finalPath: '/mobile' },
  { route: '/play', finalPath: '/play' },
  { route: '/player', finalPath: '/play?role=player' },
  { route: '/gm', finalPath: '/play?role=gm' },
  { route: '/observer', finalPath: '/play?role=observer' },
  { route: '/session', finalPath: '/play' }
];

test('mobile and PWA public routes keep installability and role entry explicit', async ({ page, request, context }) => {
  await context.grantPermissions(['notifications'], { origin: baseUrl });

  for (const expectation of routeExpectations) {
    const response = await request.get(`${baseUrl}${expectation.route}`);
    expect(response.ok(), `route ${expectation.route} should succeed`).toBeTruthy();
    const finalUrl = new URL(response.url());
    expect(
      `${finalUrl.pathname}${finalUrl.search}`,
      `route ${expectation.route} should land on ${expectation.finalPath}`,
    ).toBe(expectation.finalPath);
  }

  const manifestResponse = await request.get(`${baseUrl}/manifest.json`);
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  expect(manifest.id).toBe('/mobile');
  expect(manifest.start_url).toBe('/mobile');
  expect(Array.isArray(manifest.display_override) && manifest.display_override.length > 0).toBeTruthy();
  expect(Array.isArray(manifest.screenshots) && manifest.screenshots.length).toBeGreaterThanOrEqual(2);
  const shortcutUrls = new Set((manifest.shortcuts ?? []).map((shortcut: { url?: string }) => shortcut.url));
  expect(shortcutUrls.has('/mobile')).toBeTruthy();
  expect(shortcutUrls.has('/play')).toBeTruthy();
  expect(shortcutUrls.has('/play/continuity')).toBeTruthy();

  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: 'Mobile and PWA entry' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Install this app' })).toBeVisible();
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', /manifest\.(json|webmanifest)/);

  const swUrl = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return null;
    }

    const registration = await navigator.serviceWorker.getRegistration('/');
    if (!registration) {
      return null;
    }

    const worker = registration.active ?? registration.waiting ?? registration.installing;
    return worker?.scriptURL ?? null;
  });
  expect(swUrl).toContain('/service-worker.js');
});
