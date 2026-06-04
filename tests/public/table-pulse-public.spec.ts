import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('table pulse public route keeps live and aftermath rails separate', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/table-pulse`);
  const receiptResponse = await request.get(`${baseUrl}/table-pulse/receipts/live-and-aftermath.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('table_pulse');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.separationStatus).toBe('pass');
  expect(payload.liveRail.notificationsHref).toBe('/account/ledger/notifications');
  expect(payload.aftermathRail.workspaceHref).toBe('/account/work#aftermath-packages');
  expect(Array.isArray(payload.aftermathRail.apiRoutes)).toBeTruthy();
  expect(payload.aftermathRail.apiRoutes.length).toBeGreaterThanOrEqual(2);

  await page.goto(`${baseUrl}/table-pulse`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'TABLE PULSE separates live heat from private aftermath.' })).toBeVisible();
  await expect(page.locator('body')).toContainText('GM-controlled heat packets on the signed-in ledger notifications route.');
  await expect(page.locator('body')).toContainText('Workspace aftermath recap packages stay receipt-backed.');
  await expect(page.locator('body')).toContainText('No player surveillance or public trust scoring.');

  writeJsonArtifact('TABLE_PULSE_PUBLIC_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/table-pulse',
    receipt_route: '/table-pulse/receipts/live-and-aftermath.json',
    payload,
  });
});
