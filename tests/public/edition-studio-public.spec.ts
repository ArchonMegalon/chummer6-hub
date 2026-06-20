import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('edition studio public route stays available and points at the signed-in edition desk', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/edition-studio`);
  const receiptResponse = await request.get(`${baseUrl}/edition-studio/receipts/ruleset-heads.json`);
  const sr4PacketResponse = await request.get(`${baseUrl}/edition-studio/packets/sr4_head.json`);
  const sr5PacketResponse = await request.get(`${baseUrl}/edition-studio/packets/sr5_head.json`);
  const sr6PacketResponse = await request.get(`${baseUrl}/edition-studio/packets/sr6_head.json`);
  const missingPacketResponse = await request.get(`${baseUrl}/edition-studio/packets/not-real.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(sr4PacketResponse.status()).toBe(200);
  expect(sr5PacketResponse.status()).toBe(200);
  expect(sr6PacketResponse.status()).toBe(200);
  expect(missingPacketResponse.status()).toBe(404);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('edition_studio');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.sr4HeadMarkdownHref).toBe('/edition-studio/packets/sr4_head.md');
  expect(payload.publicBoard.sr6HeadJsonHref).toBe('/edition-studio/packets/sr6_head.json');
  expect(payload.signedInDesk.accountEntryHref).toBe('/account/edition-studio');
  expect(payload.signedInDesk.accountRedirectHref).toBe('/account/edition-studio/open');
  expect(payload.signedInDesk.accountHeadHrefTemplate).toBe('/account/edition-studio/{edition}');
  expect(payload.signedInDesk.headsApiHref).toBe('/api/v1/campaign-spine/me/edition-studio/heads');
  expect(payload.signedInDesk.headDetailApiHrefTemplate).toBe('/api/v1/campaign-spine/me/edition-studio/heads/{edition}');

  await page.goto(`${baseUrl}/edition-studio`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'EDITION STUDIO', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('EDITION STUDIO now ships a bounded first-party ruleset-head lane');
  await expect(page.locator('body')).toContainText('Signed-in edition desk');
  await expect(page.locator('body')).toContainText('Ruleset-head surface only.');

  writeJsonArtifact('EDITION_STUDIO_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/edition-studio',
    receipt_route: '/edition-studio/receipts/ruleset-heads.json',
    payload,
  });
});
