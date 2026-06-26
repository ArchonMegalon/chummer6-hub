import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const expectedTourHref = process.env.EXPECT_PROPERTYQUARRY_TOUR_HREF?.trim();
const expectedTourLabel = process.env.EXPECT_PROPERTYQUARRY_TOUR_LABEL?.trim();
const expectedTourActionLabel = process.env.EXPECT_PROPERTYQUARRY_TOUR_ACTION_LABEL?.trim();

test('propertyquarry public route stays available and points at the signed-in property desk', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/propertyquarry`);
  const receiptResponse = await request.get(`${baseUrl}/propertyquarry/receipts/property-network.json`);
  const receiptResponseLegacy = await request.get(`${baseUrl}/propertyquarry/receipts/property-network`);
  const firstPropertyResponse = await request.get(`${baseUrl}/propertyquarry/properties/northbound-research-lab.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(receiptResponseLegacy.status()).toBe(200);
  expect(firstPropertyResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  const payloadLegacy = await receiptResponseLegacy.json();
  expect(payload.horizon).toBe('propertyquarry');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.firstPropertyMarkdownHref).toBe('/propertyquarry/properties/northbound-research-lab.md');
  expect(payload.publicBoard.firstPropertyJsonHref).toBe('/propertyquarry/properties/northbound-research-lab.json');
  expect(payload.signedInDesk.accountEntryHref).toBe('/account/propertyquarry');
  expect(payload.signedInDesk.accountRedirectHref).toBe('/account/propertyquarry/open');
  expect(payload.signedInDesk.accountWorkspaceHrefTemplate).toBe('/account/propertyquarry/{propertyId}');
  expect(payload).toEqual(payloadLegacy);

  const firstPropertyPayload = await firstPropertyResponse.json();
  expect(firstPropertyPayload.style).toBe('Research Lab');
  expect(firstPropertyPayload.tour_action_href).toBe('/propertyquarry/properties/northbound-research-lab/tour');
  expect(firstPropertyPayload.tour_action_label).toBe(expectedTourActionLabel ?? 'Open 3D Tour');
  expect(firstPropertyPayload.tour_action_open_in_new_tab).toBe(false);
  if (expectedTourHref) {
    expect(firstPropertyPayload.tour_href).toBe(expectedTourHref);
  }
  if (expectedTourLabel) {
    expect(firstPropertyPayload.tour_label).toBe(expectedTourLabel);
  }
  if (expectedTourActionLabel) {
    expect(firstPropertyPayload.tour_action_label).toBe(expectedTourActionLabel);
  }

  await page.goto(`${baseUrl}/propertyquarry`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'PROPERTYQUARRY', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('each property keeps its own scene style');
  await expect(page.locator('body')).toContainText('Signed-in continuity');
  await expect(page.locator('body')).toContainText('Style: Research Lab');
  await expect(page.getByRole('link', { name: expectedTourActionLabel ?? 'Open 3D Tour' }).first()).toHaveAttribute(
    'href',
    '/propertyquarry/properties/northbound-research-lab/tour'
  );

  writeJsonArtifact('PROPERTYQUARRY_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/propertyquarry',
    receipt_route: '/propertyquarry/receipts/property-network.json',
    receipt_route_legacy: '/propertyquarry/receipts/property-network',
    payload,
    firstPropertyPayload,
  });
});
