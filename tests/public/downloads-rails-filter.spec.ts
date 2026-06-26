import { expect, test } from 'playwright/test';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('windows users see only stable and nightly in the primary downloads rail', async ({ browser }) => {
  test.setTimeout(90_000);

  const windowsUserAgent =
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';
  const page = await browser.newPage({
    userAgent: windowsUserAgent,
    viewport: { width: 1366, height: 768 },
    baseURL: baseUrl,
  });

  await page.goto('/downloads', { waitUntil: 'domcontentloaded' });

  const primarySection = page.locator('.downloads-choice-list').first();
  await expect(primarySection).toBeVisible();
  await expect(primarySection.locator('article#stable')).toBeVisible();
  await expect(primarySection.locator('article#nightly')).toBeVisible();
  await expect(primarySection.locator('article')).toHaveCount(2);
  await expect(primarySection.locator('a')).toHaveCount(2);
  await expect(page.locator('#other-downloads')).toBeVisible();
  await expect(page.locator('#other-downloads')).not.toHaveAttribute('open');

  await expect(primarySection.getByText(/Build from source/i)).toHaveCount(0);
  await expect(primarySection.locator('a.button-like')).toHaveCount(2);

  const otherSection = page.locator('#other-downloads .downloads-choice-list');
  const hiddenOtherCards = await otherSection.locator('article').count();
  expect(hiddenOtherCards).toBeGreaterThan(0);
  await expect(otherSection).toBeHidden();

  await page.locator('#other-downloads > summary').click();
  await expect(otherSection).toBeVisible();
  await expect(otherSection).toBeInViewport();
  await expect(otherSection.locator('article#linux-source')).toBeVisible();
  await expect(otherSection.locator('a.button-like', { hasText: 'Download script' })).toBeVisible();

  await page.close();
});
