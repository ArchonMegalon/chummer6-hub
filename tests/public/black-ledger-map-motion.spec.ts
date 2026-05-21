import { test, expect } from 'playwright/test';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger map exposes meaningful motion and reduced-motion-safe controls', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'networkidle' });

  const geoscapeRoot = page.locator('[data-black-ledger-geoscape-root]');
  expect(Number(await geoscapeRoot.getAttribute('data-event-count'))).toBeGreaterThan(0);
  expect(Number(await geoscapeRoot.getAttribute('data-arc-count'))).toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Recent changes' }).click();
  await expect(geoscapeRoot).toHaveAttribute('data-current-mode', 'recent-changes');
});
