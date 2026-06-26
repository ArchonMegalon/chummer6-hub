import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('jackpoint public route stays available and points at the signed-in publication desk', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/jackpoint`);
  const receiptResponse = await request.get(`${baseUrl}/jackpoint/receipts/briefing-network.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('jackpoint');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.firstBriefingMarkdownHref).toBe('/jackpoint/briefings/emerald-sprawl-briefing.md');
  expect(payload.publicBoard.firstBriefingJsonHref).toBe('/jackpoint/briefings/emerald-sprawl-briefing.json');
  expect(payload.signedInDesk.accountEntryHref).toBe('/account/jackpoint');
  expect(payload.signedInDesk.accountRedirectHref).toBe('/account/jackpoint/open');
  expect(payload.signedInDesk.publicationIndexApiHref).toBe('/api/v1/campaign-spine/me/publications');
  expect(payload.signedInDesk.publicationDetailApiHrefTemplate).toBe('/api/v1/campaign-spine/me/publications/{publicationId}');

  await page.goto(`${baseUrl}/jackpoint`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'JACKPOINT', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('JACKPOINT keeps dossiers and mission briefs readable in public');
  await expect(page.locator('body')).toContainText('Sign in for JACKPOINT');
  await expect(page.locator('body')).toContainText('Dossier and mission-brief output only.');

  writeJsonArtifact('JACKPOINT_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/jackpoint',
    receipt_route: '/jackpoint/receipts/briefing-network.json',
    payload,
  });
});
