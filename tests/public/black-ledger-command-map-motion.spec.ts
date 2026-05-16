import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger command map route is visibly distinct and exposes reduced-motion-safe controls', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/ledger/map#ledger-map`, { waitUntil: 'networkidle' });

  await expect(page.locator('.ledger-command-map')).toBeVisible();
  await expect(page.locator('#ledger-map')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Influence' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Conflict' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Recent changes' })).toBeVisible();

  const eventCount = await page.locator('[data-event-id]').count();
  const arcCount = await page.locator('.ledger-command-map__arc').count();
  expect(eventCount).toBeGreaterThan(0);
  expect(arcCount).toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Recent changes' }).click();
  await expect(page.locator('.ledger-command-map[data-current-mode="recent-changes"]')).toBeVisible();
  await page.getByRole('button', { name: 'Conflict' }).click();
  await expect(page.locator('.ledger-command-map[data-current-mode="conflict"]')).toBeVisible();

  writeJsonArtifact('BLACK_LEDGER_COMMAND_MAP_MOTION.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map#ledger-map',
    reduced_motion: true,
    event_count: eventCount,
    arc_count: arcCount,
  });
});
