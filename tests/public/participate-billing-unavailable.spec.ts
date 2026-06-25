import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const identityToken = process.env.CHUMMER_E2E_IDENTITY_TOKEN?.trim() || '';
const boardSentinel = process.env.CHUMMER_E2E_BOARD_SENTINEL?.trim() || 'board sentinel';

test('participate suppresses supporter links when billing is unavailable', async ({ browser }) => {
  test.skip(!identityToken, 'signed-in participate verification needs CHUMMER_E2E_IDENTITY_TOKEN');
  test.setTimeout(90_000);

  const parsedBaseUrl = new URL(baseUrl);
  const context = await browser.newContext();
  await context.addCookies([
    {
      name: 'chummer_hub_access_token',
      value: identityToken,
      domain: parsedBaseUrl.hostname,
      path: '/',
      httpOnly: false,
      secure: parsedBaseUrl.protocol === 'https:',
      sameSite: 'Lax',
    },
  ]);

  const page = await context.newPage();
  await page.goto(`${baseUrl}/participate`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText(boardSentinel);
  await expect(page.locator('body')).not.toContainText('Support Chummer');
  await expect(page.locator('a[href="/account/billing"]')).toHaveCount(0);
  writeJsonArtifact('PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    board_sentinel: boardSentinel,
    supporter_link_count: 0,
    supporter_copy_visible: false,
    billing_state: 'unavailable',
  });
  await page.close();
  await context.close();
});
