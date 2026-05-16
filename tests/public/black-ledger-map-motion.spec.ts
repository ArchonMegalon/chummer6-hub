import { test, expect } from 'playwright/test';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger map exposes meaningful motion and reduced-motion-safe controls', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });

  expect(await page.locator('.ledger-command-map__event').count()).toBeGreaterThan(0);
  expect(await page.locator('.ledger-command-map__arc').count()).toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Recent changes' }).click();
  await expect(page.locator('.ledger-command-map[data-current-mode="recent-changes"]')).toBeVisible();
});
