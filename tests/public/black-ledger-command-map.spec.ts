import { test, expect } from 'playwright/test';
import { writeMapJsonArtifact } from './black-ledger-map-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger command map renders with routes, controls, and fallback content', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });

  await expect(page.locator('.ledger-command-map')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Influence' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Conflict' })).toBeVisible();
  await expect(page.locator('.ledger-command-map__panel')).toBeVisible();
  await expect(page.locator('#district-rust-bazaar')).toBeVisible();

  const eventCount = await page.locator('[data-event-id]').count();
  const districtCount = await page.locator('[data-region-id]').count();

  writeMapJsonArtifact('BLACK_LEDGER_COMMAND_MAP_RENDER.generated.json', {
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map',
    event_count: eventCount,
    district_count: districtCount,
  });
});
