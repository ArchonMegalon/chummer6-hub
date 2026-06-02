import { test, expect } from 'playwright/test';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger map exposes meaningful motion and reduced-motion-safe controls', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });

  const geoscapeRoot = page.locator('.ledger-command-map__globe [data-black-ledger-geoscape-root]').first();
  await expect
    .poll(async () => Number(await geoscapeRoot.getAttribute('data-event-count')), { timeout: 10000 })
    .toBeGreaterThan(0);
  await expect
    .poll(async () => Number(await geoscapeRoot.getAttribute('data-arc-count')), { timeout: 10000 })
    .toBeGreaterThan(0);

  await geoscapeRoot.getByRole('button', { name: 'Recent changes' }).click();
  await expect(geoscapeRoot).toHaveAttribute('data-current-mode', 'recent-changes');
});
