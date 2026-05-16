import { test, expect } from 'playwright/test';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger onboarding route redirects guests to login', async ({ page }) => {
  const response = await page.goto(`${baseUrl}/account/ledger/onboarding`, { waitUntil: 'networkidle' });
  expect(response?.status()).toBe(200);
  expect(page.url()).toContain('/login?next=');
});

test('black ledger public faction package route resolves', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/factions/ashline-circle/packages`, { waitUntil: 'networkidle' });
  await expect(page.locator('body')).toContainText('Black Ledger');
});
