import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('onramp public route stays available and points at the signed-in starter desk', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/onramp`);
  const receiptResponse = await request.get(`${baseUrl}/onramp/receipts/guided-starter.json`);
  const starterPacketResponse = await request.get(`${baseUrl}/onramp/packets/starter_lane.json`);
  const recoveryPacketResponse = await request.get(`${baseUrl}/onramp/packets/recovery_lane.json`);
  const missingPacketResponse = await request.get(`${baseUrl}/onramp/packets/not-real.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(starterPacketResponse.status()).toBe(200);
  expect(recoveryPacketResponse.status()).toBe(200);
  expect(missingPacketResponse.status()).toBe(404);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('onramp');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.starterLaneMarkdownHref).toBe('/onramp/packets/starter_lane.md');
  expect(payload.publicBoard.recoveryLaneJsonHref).toBe('/onramp/packets/recovery_lane.json');
  expect(payload.signedInDesk.accountEntryHref).toBe('/account/onramp');
  expect(payload.signedInDesk.accountRedirectHref).toBe('/account/onramp/open');
  expect(payload.signedInDesk.accountStarterHref).toBe('/account/onramp/starter');
  expect(payload.signedInDesk.dashboardApiHref).toBe('/api/v1/campaign-spine/me/onramp/dashboard');
  expect(payload.signedInDesk.starterApiHref).toBe('/api/v1/campaign-spine/me/onramp/starter');
  expect(payload.signedInDesk.recoveryApiHref).toBe('/api/v1/campaign-spine/me/onramp/recovery');

  await page.goto(`${baseUrl}/onramp`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'ONRAMP', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('ONRAMP now ships a bounded first-party starter lane');
  await expect(page.locator('body')).toContainText('Signed-in starter desk');
  await expect(page.locator('body')).toContainText('Guided starter surface only.');

  writeJsonArtifact('ONRAMP_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/onramp',
    receipt_route: '/onramp/receipts/guided-starter.json',
    payload,
  });
});
