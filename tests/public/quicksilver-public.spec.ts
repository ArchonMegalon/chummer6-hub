import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('quicksilver public route stays available and points at the signed-in command deck', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/quicksilver`);
  const receiptResponse = await request.get(`${baseUrl}/quicksilver/receipts/command-network.json`);
  const packetResponse = await request.get(`${baseUrl}/quicksilver/packets/command_deck.json`);
  const jumpTargetsResponse = await request.get(`${baseUrl}/quicksilver/packets/jump_targets.json`);
  const missingPacketResponse = await request.get(`${baseUrl}/quicksilver/packets/not-real.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(packetResponse.status()).toBe(200);
  expect(jumpTargetsResponse.status()).toBe(200);
  expect(missingPacketResponse.status()).toBe(404);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('quicksilver');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.commandDeckMarkdownHref).toBe('/quicksilver/packets/command_deck.md');
  expect(payload.publicBoard.jumpTargetsJsonHref).toBe('/quicksilver/packets/jump_targets.json');
  expect(payload.signedInBench.accountEntryHref).toBe('/account/quicksilver');
  expect(payload.signedInBench.accountRedirectHref).toBe('/account/quicksilver/open');
  expect(payload.signedInBench.commandDeckApiHref).toBe('/api/v1/campaign-spine/me/quicksilver/command-deck');
  expect(payload.signedInBench.jumpTargetsApiHref).toBe('/api/v1/campaign-spine/me/quicksilver/jump-targets');
  expect(Array.isArray(payload.focusTargets)).toBeTruthy();
  expect(payload.focusTargets.length).toBeGreaterThanOrEqual(5);

  await page.goto(`${baseUrl}/quicksilver`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Quicksilver', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('Quicksilver now ships a real first-party command deck');
  await expect(page.locator('body')).toContainText('Sign in for Quicksilver');
  await expect(page.locator('body')).toContainText('It does not hide legality, invent background automation, or turn stale cached views into authority');

  writeJsonArtifact('QUICKSILVER_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/quicksilver',
    receipt_route: '/quicksilver/receipts/command-network.json',
    payload,
  });
});
