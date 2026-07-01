import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const viewportSmokeTimeoutMs = Number(process.env.CHUMMER_MOBILE_PWA_VIEWPORT_TIMEOUT_MS || '240000');

const viewports = [
  { name: 'phone-390', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop-1366', width: 1366, height: 768 },
];

const routes = [
  { path: '/mobile', expected: 'Mobile and PWA entry' },
  { path: '/mobile/player', expected: 'Player entry' },
  { path: '/mobile/gm', expected: 'GM entry' },
  { path: '/mobile/observer', expected: 'Observer entry' },
  { path: '/play', expected: 'Player entry' },
  { path: '/play/continuity', expected: 'NEXUS-PAN continuity' },
];

test('core mobile PWA routes fit phone tablet and desktop viewports', async ({ browser }) => {
  test.setTimeout(viewportSmokeTimeoutMs);
  const results: Array<Record<string, unknown>> = [];
  const failures: string[] = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport });
    page.setDefaultNavigationTimeout(30000);
    await page.route('**/*', async (route) => {
      if (route.request().resourceType() === 'media') {
        await route.abort();
        return;
      }

      await route.continue();
    });

    for (const route of routes) {
      let status = 0;
      let navigationError = '';
      let overflowX = 0;
      try {
        const response = await page.goto(route.path, { waitUntil: 'domcontentloaded', timeout: 30000 });
        status = response?.status() ?? 0;
        const bodyText = await page.locator('body').textContent({ timeout: 10000 }).catch(() => '');
        const title = await page.title().catch(() => '');
        const routeReady = bodyText?.includes(route.expected)
          || title.includes(route.expected)
          || bodyText?.includes('LIVE-SESSION TURN COMPANION')
          || title.includes('Chummer Mobile Turn Companion');
        if (!routeReady) {
          failures.push(`${route.path} ${viewport.name} missing expected shell ${route.expected}`);
        }
        overflowX = await page.evaluate(() => Math.max(
          document.documentElement.scrollWidth,
          document.body?.scrollWidth || 0,
        ) - window.innerWidth);
      } catch (error) {
        navigationError = error instanceof Error ? error.message : String(error);
        failures.push(`${route.path} ${viewport.name} navigation failed: ${navigationError}`);
      }

      if (status >= 500 || status < 200) {
        failures.push(`${route.path} ${viewport.name} returned HTTP ${status}`);
      }
      if (overflowX > 1) {
        failures.push(`${route.path} ${viewport.name} has ${Math.round(overflowX)}px horizontal overflow`);
      }

      results.push({
        route: route.path,
        viewport: viewport.name,
        width: viewport.width,
        height: viewport.height,
        status,
        overflow_x: overflowX,
        navigation_error: navigationError,
      });
    }

    await page.close();
  }

  writeJsonArtifact('MOBILE_PWA_VIEWPORT_SMOKE.generated.json', {
    contractName: 'chummer.mobile_pwa_viewport_smoke.v1',
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    base_url: baseUrl,
    routes: routes.map((route) => route.path),
    route_count: routes.length,
    viewport_count: viewports.length,
    results,
    failures,
  });

  expect(failures).toEqual([]);
});
