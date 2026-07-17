import { test, expect } from 'playwright/test';

const baseUrl = (process.env.CHUMMER_HUB_BASE_URL ?? 'http://127.0.0.1:8091').replace(/\/$/, '');

const routeExpectations: Array<{ route: string; finalPath: string }> = [
  { route: '/mobile', finalPath: '/mobile' },
  { route: '/pwa', finalPath: '/mobile' },
  { route: '/play', finalPath: '/mobile/player' },
  { route: '/player', finalPath: '/mobile/player' },
  { route: '/jammer', finalPath: '/mobile/player' },
  { route: '/gm', finalPath: '/mobile/gm' },
  { route: '/observer', finalPath: '/mobile/observer' },
  { route: '/session', finalPath: '/mobile/player' }
];

test('mobile and PWA public routes keep installability and role entry explicit', async ({ page, request, context }) => {
  test.setTimeout(90000);
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
  expect(manifest.name).toBe('Chummer Turn Companion');
  expect(manifest.short_name).toBe('Chummer Play');
  expect(manifest.start_url).toBe('/mobile/player');
  expect(manifest.scope).toBe('/mobile/');
  expect(Array.isArray(manifest.display_override) && manifest.display_override.length > 0).toBeTruthy();
  expect(Array.isArray(manifest.screenshots) && manifest.screenshots.length).toBeGreaterThanOrEqual(2);
  const shortcutUrls = new Set((manifest.shortcuts ?? []).map((shortcut: { url?: string }) => shortcut.url));
  expect(shortcutUrls.has('/mobile/player')).toBeTruthy();
  expect(shortcutUrls.has('/mobile/gm')).toBeTruthy();
  expect([...shortcutUrls].every((url) => typeof url !== 'string' || !url.includes('?'))).toBeTruthy();
  expect(shortcutUrls.has('/app?command=character_roster')).toBeFalsy();

  const pwaLedgerResponse = await request.get(`${baseUrl}/mobile/pwa/ledger.json`);
  expect(pwaLedgerResponse.ok()).toBeTruthy();
  const ledgerPayload = await pwaLedgerResponse.json();
  expect(ledgerPayload.mode).toBe("mobile_pwa_living_world");
  expect(["opt_in_required", "no_world_data", "live", "world_not_followed"]).toContain(ledgerPayload.status);
  expect(ledgerPayload.updates_route).toBe("/mobile/pwa/ledger.json");
  if (ledgerPayload.status === "opt_in_required") {
    expect(ledgerPayload.opt_in_route).toBe("/account");
  } else if (ledgerPayload.status === "live") {
    expect(ledgerPayload.world).toBeTruthy();
    expect(Array.isArray(ledgerPayload.top_districts)).toBeTruthy();
    expect(typeof ledgerPayload.continuity).toBe("object");
    expect(typeof ledgerPayload.continuity?.turn).toBe("number");
    expect(Array.isArray(ledgerPayload.continuity?.events)).toBeTruthy();
    expect(ledgerPayload.tracker).toEqual(expect.objectContaining({ turn_route: expect.any(String), newsreel_route: expect.any(String) }));
  } else if (ledgerPayload.status === "world_not_followed") {
    expect(ledgerPayload.world).toBeTruthy();
    expect(ledgerPayload.world?.turn_headline).toBe("Follow this world to reveal the live turn headline.");
    expect(ledgerPayload.world?.world_turn).toBeNull();
    expect(Array.isArray(ledgerPayload.top_districts)).toBeTruthy();
    expect(ledgerPayload.top_districts).toHaveLength(0);
    expect(ledgerPayload.hot_district).toBeNull();
    expect(ledgerPayload.move_district).toBeNull();
    expect(ledgerPayload.continuity).toBeNull();
    expect(ledgerPayload.summary?.follow_hint).toContain("preferences");
    expect(ledgerPayload.tracker).toEqual(expect.objectContaining({ turn_route: null, newsreel_route: null }));
  } else {
    expect(ledgerPayload.status).toBe("no_world_data");
  }

  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main[data-play-surface="install-only"]')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Keep your runner ready at the table.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Install app' })).toBeVisible();
  await expect(page.locator('[data-mobile-app-inline-qr]')).toBeVisible();
  await expect(page.locator('[data-pwa-ledger-status]')).toHaveCount(0);
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', /manifest\.(json|webmanifest)/);

  const readRegisteredWorkerUrl = async () => page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return '';
    }

    const registration = await navigator.serviceWorker.getRegistration('/');
    if (!registration) {
      return '';
    }

    const worker = registration.active ?? registration.waiting ?? registration.installing;
    return worker?.scriptURL ?? '';
  });
  await expect.poll(readRegisteredWorkerUrl, { timeout: 15000 }).toContain('/service-worker.js');
  const swUrl = await readRegisteredWorkerUrl();

  const readReadyWorkerUrl = async () => page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return '';
    }

    const registration = await navigator.serviceWorker.ready;
    return registration.active?.scriptURL ?? '';
  });
  await expect.poll(readReadyWorkerUrl, { timeout: 15000 }).toContain('/service-worker.js');
  const readyWorkerUrl = await readReadyWorkerUrl();

  const controllerWorkerUrl = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return null;
    }

    if (navigator.serviceWorker.controller) {
      return navigator.serviceWorker.controller.scriptURL;
    }

    await new Promise<void>((resolve) => {
      const timeout = window.setTimeout(resolve, 3000);
      navigator.serviceWorker.addEventListener(
        'controllerchange',
        () => {
          window.clearTimeout(timeout);
          resolve();
        },
        { once: true },
      );
    });

    return navigator.serviceWorker.controller?.scriptURL ?? null;
  });

  if (controllerWorkerUrl === null) {
    await page.reload({ waitUntil: 'domcontentloaded' });
  }

  const readControlledWorkerUrl = async () => page.evaluate(() => {
    if (!('serviceWorker' in navigator)) {
      return '';
    }

    return navigator.serviceWorker.controller?.scriptURL ?? '';
  });
  if (!controllerWorkerUrl) {
    await expect.poll(readControlledWorkerUrl, { timeout: 10000 }).toContain('/service-worker.js');
  }
  const controlledWorkerUrl = controllerWorkerUrl || await readControlledWorkerUrl();
  expect(controlledWorkerUrl).toContain('/service-worker.js');
});

test('public role aliases discard query and fragment state for GET and HEAD', async ({ page, request }) => {
  const aliases = [
    { route: '/player', target: '/mobile/player' },
    { route: '/jammer', target: '/mobile/player' },
    { route: '/gm', target: '/mobile/gm' },
    { route: '/observer', target: '/mobile/observer' },
  ];

  for (const alias of aliases) {
    const head = await request.fetch(
      `${baseUrl}${alias.route}?sessionId=synthetic-alias-proof&deviceId=synthetic-alias-proof`,
      { method: 'HEAD', maxRedirects: 0 },
    );
    expect(head.status(), `${alias.route} HEAD should redirect before routing`).toBe(302);
    expect(head.headers()['location'], `${alias.route} HEAD should emit a clean canonical target`).toBe(`${alias.target}#`);
    const cacheControl = head.headers()['cache-control'] ?? '';
    for (const token of ['private', 'no-store', 'no-cache', 'max-age=0']) {
      expect(cacheControl.toLowerCase(), `${alias.route} HEAD should include ${token}`).toContain(token);
    }
    expect(head.headers()['pragma']).toBe('no-cache');
    expect(head.headers()['expires']).toBe('0');
    expect(head.headers()['referrer-policy']).toBe('no-referrer');
  }

  await page.goto(
    `${baseUrl}/jammer?sessionId=synthetic-alias-proof&deviceId=synthetic-alias-proof#private-fragment-proof`,
    { waitUntil: 'domcontentloaded' },
  );
  const finalUrl = new URL(page.url());
  expect(finalUrl.pathname).toBe('/mobile/player');
  expect(finalUrl.search).toBe('');
  expect(finalUrl.hash).toBe('');
  await expect(page.locator('main[data-play-surface="install-only"]')).toBeVisible();
});

test('public install shell does not request private ledger data', async ({ page }) => {
  let ledgerRequests = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/mobile/pwa/ledger.json') {
      ledgerRequests += 1;
    }
  });
  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(750);

  expect(ledgerRequests).toBe(0);
  await expect(page.locator('main[data-play-surface="install-only"]')).toBeVisible();
  await expect(page.locator('[data-pwa-ledger-status]')).toHaveCount(0);
  await expect(page.locator('[data-pwa-ledger-turn-route]')).toHaveCount(0);
});
