import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('run control public route stays available and points at the signed-in control desk', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/run-control`);
  const receiptResponse = await request.get(`${baseUrl}/run-control/receipts/control-network.json`);
  const sessionPacketResponse = await request.get(`${baseUrl}/run-control/packets/session_board.json`);
  const continuityPacketResponse = await request.get(`${baseUrl}/run-control/packets/continuity_board.json`);
  const missingPacketResponse = await request.get(`${baseUrl}/run-control/packets/not-real.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(sessionPacketResponse.status()).toBe(200);
  expect(continuityPacketResponse.status()).toBe(200);
  expect(missingPacketResponse.status()).toBe(404);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('run_control');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.sessionBoardMarkdownHref).toBe('/run-control/packets/session_board.md');
  expect(payload.publicBoard.continuityBoardJsonHref).toBe('/run-control/packets/continuity_board.json');
  expect(payload.signedInDesk.accountEntryHref).toBe('/account/run-control');
  expect(payload.signedInDesk.accountRedirectHref).toBe('/account/run-control/open');
  expect(payload.signedInDesk.dashboardApiHref).toBe('/api/v1/campaign-spine/me/run-control/dashboard');
  expect(payload.signedInDesk.runDetailApiHrefTemplate).toBe('/api/v1/campaign-spine/me/run-control/runs/{runId}');

  await page.goto(`${baseUrl}/run-control`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'RUN CONTROL', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('RUN CONTROL now ships a real first-party GM operations lane');
  await expect(page.locator('body')).toContainText('Signed-in control desk');
  await expect(page.locator('body')).toContainText('GM-control surface only.');

  writeJsonArtifact('RUN_CONTROL_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/run-control',
    receipt_route: '/run-control/receipts/control-network.json',
    payload,
  });
});
