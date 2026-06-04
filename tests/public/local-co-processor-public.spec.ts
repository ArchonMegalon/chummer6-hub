import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('local co-processor public route stays receipt-backed and points at the signed-in profile desk', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/local-co-processor`);
  const receiptResponse = await request.get(`${baseUrl}/local-co-processor/receipts/optional-acceleration.json`);
  const capabilityPacketResponse = await request.get(`${baseUrl}/local-co-processor/packets/capability_matrix.json`);
  const policyPacketResponse = await request.get(`${baseUrl}/local-co-processor/packets/policy_boundary.json`);
  const missingPacketResponse = await request.get(`${baseUrl}/local-co-processor/packets/not-real.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(capabilityPacketResponse.status()).toBe(200);
  expect(policyPacketResponse.status()).toBe(200);
  expect(missingPacketResponse.status()).toBe(404);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('local_co_processor');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.capabilityMatrixMarkdownHref).toBe('/local-co-processor/packets/capability_matrix.md');
  expect(payload.publicBoard.policyBoundaryJsonHref).toBe('/local-co-processor/packets/policy_boundary.json');
  expect(payload.signedInDesk.accountEntryHref).toBe('/account/local-co-processor');
  expect(payload.signedInDesk.accountRedirectHref).toBe('/account/local-co-processor/open');
  expect(payload.signedInDesk.accountProfileHrefTemplate).toBe('/account/local-co-processor/{profile}');
  expect(payload.signedInDesk.capabilitiesApiHref).toBe('/api/v1/campaign-spine/me/local-co-processor/capabilities');
  expect(payload.signedInDesk.policyApiHref).toBe('/api/v1/campaign-spine/me/local-co-processor/policy');
  expect(Array.isArray(payload.profiles)).toBeTruthy();
  expect(payload.profiles.length).toBe(3);

  await page.goto(`${baseUrl}/local-co-processor`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'LOCAL CO-PROCESSOR', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('LOCAL CO-PROCESSOR now ships a bounded first-party optional-acceleration lane');
  await expect(page.locator('body')).toContainText('Signed-in optional profile desk');
  await expect(page.locator('body')).toContainText('LOCAL CO-PROCESSOR does not move truth into local runtime');

  writeJsonArtifact('LOCAL_CO_PROCESSOR_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/local-co-processor',
    receipt_route: '/local-co-processor/receipts/optional-acceleration.json',
    payload,
  });
});
