import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('homepage and ledger routes use the globe as the primary render surface', async ({ page }) => {
  const results: Array<Record<string, unknown>> = [];
  for (const route of ['/', '/ledger', '/ledger/map']) {
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });
    const root = page.locator('[data-black-ledger-geoscape-root]').first();
    await expect(root).toHaveAttribute('data-ready', 'true');
    await expect(root.locator('canvas.black-ledger-geoscape__canvas')).toBeVisible();
    const box = await root.boundingBox();
    results.push({
      route,
      renderer: await root.getAttribute('data-renderer'),
      ready: await root.getAttribute('data-ready'),
      height: box?.height ?? 0,
    });
  }

  writeJsonArtifact('BLACK_LEDGER_GLOBE_RENDER.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    results,
  });
});
