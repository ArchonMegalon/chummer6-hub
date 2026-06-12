import { test, expect, type Response } from 'playwright/test';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const gotoOptions = { waitUntil: 'domcontentloaded' as const, timeout: 45000 };

test('black ledger onboarding route redirects guests to login', async ({ page }) => {
  test.setTimeout(90000);
  let response = null as Response | null;
  try {
    response = await page.goto(`${baseUrl}/account/ledger/onboarding`, gotoOptions);
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    if (!message.includes('net::ERR_ABORTED')) {
      throw error;
    }
  }

  await expect(page).toHaveURL(/\/login\?next=/);
  if (response) {
    expect(response.status()).toBe(200);
  }
  expect(page.url()).toContain('/login?next=');
});

test('black ledger public faction package route resolves', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/factions/ashline-circle/packages`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText('Black Ledger');
});
