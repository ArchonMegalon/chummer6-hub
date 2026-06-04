import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('community hub public route stays receipt-backed and points at the signed-in board', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/community`);
  const receiptResponse = await request.get(`${baseUrl}/community/receipts/open-run-network.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('community_hub');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.boardMarkdownHref).toBe('/community/open-runs/open_run_board.md');
  expect(payload.publicBoard.boardJsonHref).toBe('/community/open-runs/open_run_board.json');
  expect(payload.signedInBench.accountEntryHref).toBe('/account/community');
  expect(payload.signedInBench.accountRedirectHref).toBe('/account/community/open');
  expect(payload.signedInBench.openRunIndexApiHref).toBe('/api/v1/campaign-spine/me/open-runs');
  expect(payload.signedInBench.openRunDetailApiHrefTemplate).toBe('/api/v1/campaign-spine/me/open-runs/{openRunId}');

  await page.goto(`${baseUrl}/community`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Community Hub', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('Community Hub now ships a real first-party open-run network');
  await expect(page.locator('body')).toContainText('Sign in for Community Hub');
  await expect(page.locator('body')).toContainText('Meeting tools and public venues are handoff lanes only.');

  writeJsonArtifact('COMMUNITY_HUB_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/community',
    receipt_route: '/community/receipts/open-run-network.json',
    payload,
  });
});
