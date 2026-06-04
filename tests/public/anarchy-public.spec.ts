import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('anarchy public route stays receipt-backed and shipped as a rules-light lane', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/anarchy`);
  const receiptResponse = await request.get(`${baseUrl}/anarchy/receipts/runtime.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('anarchy');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.rulesetId).toBe('shadowrun_anarchy');
  expect(payload.playShell.playHref).toBe('/play/anarchy');
  expect(payload.playShell.ledgerHref).toBe('/ledger/anarchy');
  expect(payload.exportLane.exportJsonHref).toBe('/anarchy/export/runner.json');
  expect(payload.exportLane.explainReceiptHref).toBe('/anarchy/receipts/explain.json');
  expect(payload.publicProfile.verdictLabel).toBe('Shipped rules-light lane');
  expect(payload.dispatchLane.receiptAnchored).toBeTruthy();

  await page.goto(`${baseUrl}/anarchy`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Shadowrun Anarchy', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('A shipped rules-light lane for mobile play, dispatches, faction consequence, and fast continuity.');
  await expect(page.locator('body')).toContainText('Shipped rules-light lane for Black Ledger, dispatches, and mobile play.');
  await expect(page.locator('body')).toContainText('Not full book-level rules completeness.');

  writeJsonArtifact('ANARCHY_PUBLIC_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/anarchy',
    receipt_route: '/anarchy/receipts/runtime.json',
    payload,
  });
});
