import { test, expect } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger command map renders with routes, controls, and fallback content', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'networkidle' });

  await expect(page.locator('.ledger-command-map [data-black-ledger-geoscape-root][data-ready="true"]')).toBeVisible();
  await expect(page.locator('.black-ledger-geoscape__canvas')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Influence' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Conflict' })).toBeVisible();
  await expect(page.locator('.black-ledger-geoscape__panel')).toBeVisible();
  await expect(page.locator('#district-rust-bazaar')).toBeVisible();
  await expect(page.locator('[data-geoscape-fallback] svg')).toHaveCount(1);

  const eventCount = await page.locator('.black-ledger-geoscape__list--static li').count();
  const districtCount = await page.locator('[data-region-id]').count();

  writeJsonArtifact('BLACK_LEDGER_GLOBE_RENDER.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map',
    event_count: eventCount,
    district_count: districtCount,
    renderer: await page.locator('[data-black-ledger-geoscape-root]').getAttribute('data-renderer'),
    fallback_present: await page.locator('[data-geoscape-fallback]').count(),
  });
});
