import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('ghostwire public route stays receipt-backed and shipped as a replay lane', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/ghostwire`);
  const receiptResponse = await request.get(`${baseUrl}/ghostwire/receipts/replay-network.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.horizon).toBe('ghostwire');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.replayTimelineMarkdownHref).toBe('/ghostwire/after-action/replay_timeline.md');
  expect(payload.publicBoard.replayTimelineJsonHref).toBe('/ghostwire/after-action/replay_timeline.json');
  expect(payload.publicBoard.afterActionReportJsonHref).toBe('/ghostwire/after-action/after_action_report.json');
  expect(payload.publicBoard.consequenceChainJsonHref).toBe('/ghostwire/after-action/consequence_chain.json');
  expect(payload.boundaries.transcriptTruth).toBe('Not claimed');

  await page.goto(`${baseUrl}/ghostwire`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'GHOSTWIRE' })).toBeVisible();
  await expect(page.locator('body')).toContainText('GHOSTWIRE now ships first-party after-action packet rails');
  await expect(page.locator('body')).toContainText('Replay stays receipt-backed and public-safe.');

  writeJsonArtifact('GHOSTWIRE_PUBLIC_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ghostwire',
    receipt_route: '/ghostwire/receipts/replay-network.json',
    payload,
  });
});
