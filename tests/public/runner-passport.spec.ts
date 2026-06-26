import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('runner passport public route stays available and points at the signed-in continuity bench', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/passport`);
  const receiptResponse = await request.get(`${baseUrl}/passport/receipts/identity-network.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('runner_passport');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.runnerReturnMarkdownHref).toBe('/passport/runner_return_posture.md');
  expect(payload.publicBoard.runnerReturnJsonHref).toBe('/passport/runner_return_posture.json');
  expect(payload.signedInBench.accountEntryHref).toBe('/account/passport');
  expect(payload.signedInBench.accountRedirectHref).toBe('/account/passport/open');
  expect(payload.signedInBench.liveNotificationsHref).toBe('/account/ledger/notifications');
  expect(payload.signedInBench.aftermathHref).toBe('/account/work#aftermath-packages');

  await page.goto(`${baseUrl}/passport`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Runner Passport', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('Runner Passport keeps your public participation history');
  await expect(page.locator('body')).toContainText('Sign in for Runner Passport');
  await expect(page.locator('body')).toContainText('Private identity links, moderation details, and account recovery stay signed in.');

  writeJsonArtifact('RUNNER_PASSPORT_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/passport',
    receipt_route: '/passport/receipts/identity-network.json',
    payload,
  });
});
