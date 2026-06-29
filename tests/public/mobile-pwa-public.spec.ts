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
  await expect(page.getByRole('heading', { name: 'Mobile and PWA entry' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Black Ledger live tracker' })).toBeVisible();
  await expect(page.locator('[data-pwa-ledger-status]')).toBeVisible();
  await expect(page.locator('[data-pwa-ledger-summary]')).toBeVisible();
  await expect(page.locator('[data-pwa-ledger-follow-state]')).toBeVisible();
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

  const readyWorkerUrl = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) {
      return null;
    }

    const registration = await navigator.serviceWorker.ready;
    return registration.active?.scriptURL ?? null;
  });
  expect(readyWorkerUrl).toContain('/service-worker.js');

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

  const controlledWorkerUrl = controllerWorkerUrl ?? await page.evaluate(() => {
    if (!('serviceWorker' in navigator)) {
      return null;
    }

    return navigator.serviceWorker.controller?.scriptURL ?? null;
  });
  expect(controlledWorkerUrl).toContain('/service-worker.js');
});

test('mobile ledger stream clears stale live detail links on followed-world fallback', async ({ page }) => {
  let ledgerCalls = 0;
  await page.route('**/api/v1/accounts/me/preferences', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        blackLedgerNewsEmail: true,
        blackLedgerWorldsFollowed: ['other-world']
      })
    });
  });
  await page.route('**/mobile/pwa/ledger.json', async (route) => {
    ledgerCalls += 1;
    const livePayload = {
      mode: 'mobile_pwa_living_world',
      status: 'live',
      status_label: 'Live board snapshot',
      world: {
        world_id: 'seattle-live',
        world_name: 'Seattle Live',
        world_turn: 42,
        turn_headline: 'Heat rises in Redmond'
      },
      summary: {
        hot_district: 'Redmond is currently the hottest district with heat 82.',
        hot_shift: 'Downtown moved this turn by +7.',
        follow_hint: null
      },
      followed_worlds: [],
      top_districts: [{ name: 'Redmond', heat: 82, delta: 7, influence: 3, trend: 'rising' }],
      hot_district: { name: 'Redmond', heat: 82, delta: 7 },
      move_district: { name: 'Downtown', delta: 7 },
      tracker: {
        update_interval_seconds: 30,
        turn_map_route: '/ledger/map',
        turn_route: '/ledger/turns/42',
        newsreel_route: '/ledger/turns/42/newsreel.json',
        world_status: 'live'
      },
      continuity: {
        turn: 42,
        turn_summary: 'The board moved.',
        turn_route: '/ledger/turns/42',
        events: []
      },
      updates_route: '/mobile/pwa/ledger.json',
      generated_at_utc: '2026-06-29T12:00:00Z'
    };
    const gatedPayload = {
      mode: 'mobile_pwa_living_world',
      status: 'world_not_followed',
      status_label: 'Followed world not active',
      world: {
        world_id: 'seattle-live',
        world_name: 'Seattle Live',
        world_turn: 42,
        turn_headline: 'Follow this world to reveal the live turn headline.'
      },
      summary: {
        hot_district: 'Follow this world to reveal live heat tracking.',
        hot_shift: 'Follow this world to reveal live movement changes.',
        follow_hint: 'Enable or select this world in Black Ledger preferences.'
      },
      followed_worlds: ['other-world'],
      top_districts: [],
      hot_district: null,
      move_district: null,
      tracker: {
        update_interval_seconds: 30,
        turn_map_route: '/ledger/map',
        turn_route: null,
        newsreel_route: null,
        world_status: 'live'
      },
      continuity: null,
      updates_route: '/mobile/pwa/ledger.json',
      generated_at_utc: '2026-06-29T12:00:30Z'
    };

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ledgerCalls === 1 ? livePayload : gatedPayload)
    });
  });

  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'domcontentloaded' });

  const turnRoute = page.locator('[data-pwa-ledger-turn-route]');
  const newsreelRoute = page.locator('[data-pwa-ledger-newsreel-route]');
  await expect(turnRoute).toHaveAttribute('href', '/ledger/turns/42');
  await expect(newsreelRoute).toHaveAttribute('href', '/ledger/turns/42/newsreel.json');

  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));

  await expect.poll(async () => await turnRoute.getAttribute('href')).toBeNull();
  await expect.poll(async () => await newsreelRoute.getAttribute('href')).toBeNull();
  await expect(turnRoute).toHaveText('Follow this world to open live turn detail');
  await expect(newsreelRoute).toHaveText('Follow this world to open live newsreel');
  await expect(page.locator('[data-pwa-ledger-heat-score]')).toHaveText('Follow required');
});
