import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('runsite public route stays receipt-backed and points at the signed-in prep bench', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/runsites`);
  const receiptResponse = await request.get(`${baseUrl}/runsites/receipts/prep-network.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('runsite');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.firstPackMarkdownHref).toBe('/runsites/packs/redmond-dockyard-pack.md');
  expect(payload.publicBoard.firstPackJsonHref).toBe('/runsites/packs/redmond-dockyard-pack.json');
  expect(payload.signedInBench.accountEntryHref).toBe('/account/runsites');
  expect(payload.signedInBench.accountRedirectHref).toBe('/account/runsites/open');
  expect(payload.signedInBench.workspaceIndexApiHref).toBe('/api/v1/campaign-spine/me/workspace-digests');
  expect(payload.signedInBench.runIndexApiHref).toBe('/api/v1/campaign-spine/me/runs');

  await page.goto(`${baseUrl}/runsites`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'RUNSITE', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('RUNSITE now ships as a real prep network');
  await expect(page.locator('body')).toContainText('Signed-in prep bench');
  await expect(page.locator('body')).toContainText('Spatial-prep packet only.');

  writeJsonArtifact('RUNSITE_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/runsites',
    receipt_route: '/runsites/receipts/prep-network.json',
    payload,
  });
});
