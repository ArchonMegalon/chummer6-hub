import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('creator os public route stays receipt-backed and points at the signed-in publication desk', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/creator`);
  const receiptResponse = await request.get(`${baseUrl}/creator/receipts/publication-network.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('creator_os');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.boardMarkdownHref).toBe('/creator/packets/publication_board.md');
  expect(payload.publicBoard.boardJsonHref).toBe('/creator/packets/publication_board.json');
  expect(payload.signedInBench.accountEntryHref).toBe('/account/creator');
  expect(payload.signedInBench.accountRedirectHref).toBe('/account/creator/open');
  expect(payload.signedInBench.publicationDetailHrefTemplate).toBe('/account/creator/{publicationId}');
  expect(payload.signedInBench.publicDetailHrefTemplate).toBe('/artifacts/publications/{publicationId}');

  await page.goto(`${baseUrl}/creator`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Creator OS', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('Creator OS now ships a real first-party publication network');
  await expect(page.locator('body')).toContainText('Sign in for Creator OS');
  await expect(page.locator('body')).toContainText('External creator tools may assist rendering or promotion, but Chummer owns publication truth');

  writeJsonArtifact('CREATOR_OS_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/creator',
    receipt_route: '/creator/receipts/publication-network.json',
    payload,
  });
});
