import { test, expect } from '@playwright/test';

test('black ledger onboarding route redirects guests to login', async ({ page }) => {
  const response = await page.goto('/account/ledger/onboarding');
  expect(response?.status()).toBeGreaterThanOrEqual(300);
});

test('black ledger public faction package route resolves', async ({ page }) => {
  await page.goto('/ledger/factions/ashline-circle/packages');
  await expect(page.locator('body')).toContainText('Black Ledger');
});
