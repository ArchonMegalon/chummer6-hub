import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const expectedTourHref = process.env.EXPECT_RUNSITE_TOUR_HREF?.trim();
const expectedTourLabel = process.env.EXPECT_RUNSITE_TOUR_LABEL?.trim();
const expectedTourActionLabel = process.env.EXPECT_RUNSITE_TOUR_ACTION_LABEL?.trim();

test('runsite public route stays available and points at the signed-in prep bench', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/runsites`);
  const receiptResponse = await request.get(`${baseUrl}/runsites/receipts/prep-network.json`);
  const firstPackResponse = await request.get(`${baseUrl}/runsites/packs/redmond-dockyard-pack.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(firstPackResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('runsite');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.firstPackMarkdownHref).toBe('/runsites/packs/redmond-dockyard-pack.md');
  expect(payload.publicBoard.firstPackJsonHref).toBe('/runsites/packs/redmond-dockyard-pack.json');
  expect(payload.signedInBench.accountEntryHref).toBe('/account/runsites');
  expect(payload.signedInBench.accountRedirectHref).toBe('/account/runsites/open');
  expect(payload.signedInBench.workspaceIndexApiHref).toBe('/api/v1/campaign-spine/me/workspace-digests');
  expect(payload.signedInBench.runIndexApiHref).toBe('/api/v1/campaign-spine/me/runs');

  const packPayload = await firstPackResponse.json();
  expect(packPayload.style).toBe('Research Lab');
  expect(packPayload.tour_action_href).toBe('/runsites/packs/redmond-dockyard-pack/tour');
  expect(packPayload.tour_action_label).toBe(expectedTourActionLabel ?? 'Open 3D Tour');
  expect(packPayload.tour_action_open_in_new_tab).toBe(false);
  if (expectedTourHref) {
    expect(packPayload.tour_href).toBe(expectedTourHref);
  }
  if (expectedTourLabel) {
    expect(packPayload.tour_label).toBe(expectedTourLabel);
  }
  if (expectedTourActionLabel) {
    expect(packPayload.tour_action_label).toBe(expectedTourActionLabel);
  }

  await page.goto(`${baseUrl}/runsites`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'RUNSITE', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('each runsite keeps its own scene style');
  await expect(page.locator('body')).toContainText('Signed-in prep bench');
  await expect(page.locator('body')).toContainText('Spatial-prep guide only.');
  await expect(page.locator('body')).toContainText('Style: Research Lab');
  await expect(page.getByRole('link', { name: expectedTourActionLabel ?? 'Open 3D Tour' }).first()).toHaveAttribute('href', '/runsites/packs/redmond-dockyard-pack/tour');

  writeJsonArtifact('RUNSITE_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/runsites',
    receipt_route: '/runsites/receipts/prep-network.json',
    first_pack_route: '/runsites/packs/redmond-dockyard-pack.json',
    payload,
    packPayload,
  });
});
