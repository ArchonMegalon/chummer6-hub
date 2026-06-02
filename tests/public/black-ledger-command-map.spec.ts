import { test, expect } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger command map renders with routes, controls, and fallback content', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });

  const root = page.locator('#ledger-map [data-black-ledger-geoscape-root]').first();
  await expect(root).toBeVisible();
  await expect(root.locator('.black-ledger-geoscape__canvas')).toBeVisible();
  await expect(root.getByRole('button', { name: 'Influence' })).toBeVisible();
  await expect(root.getByRole('button', { name: 'Replay pressure' })).toBeVisible();
  await expect(root.locator('.black-ledger-geoscape__panel')).toBeVisible();
  await expect(root.locator('.black-ledger-geoscape__fallback-list')).toBeVisible();

  const eventCount = await root.locator('.black-ledger-geoscape__list--static li').count();
  const factionCount = Number(await root.getAttribute('data-faction-count'));
  const districtCount = Number(await root.getAttribute('data-district-count'));
  expect(factionCount).toBeGreaterThanOrEqual(6);
  expect(districtCount).toBeGreaterThanOrEqual(8);

  writeJsonArtifact('BLACK_LEDGER_GLOBE_RENDER.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map',
    event_count: eventCount,
    faction_count: factionCount,
    district_count: districtCount,
    renderer: await root.getAttribute('data-renderer'),
    fallback_present: await root.locator('.black-ledger-geoscape__fallback-list').count(),
  });
});
