import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('alice public route stays bounded and receipt-backed', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/alice`);
  const receiptResponse = await request.get(`${baseUrl}/alice/receipts/build-ghost.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.facePopStatus).toBe('Public concierge only');
  expect(payload.engineStatus).toBe('First-party compare/apply only');
  expect(payload.canonicalLane).toContain('Build Ghost compare bench');
  expect(Array.isArray(payload.actions)).toBeTruthy();
  expect(payload.actions.some((item: { href?: string }) => item.href === '/alice')).toBeTruthy();

  await page.goto(`${baseUrl}/alice`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'ALICE' })).toBeVisible();
  await expect(page.locator('body')).toContainText('The experiment should leave behind receipts, not vibes.');
  await expect(page.locator('body')).toContainText('Build ghost compare brief');

  writeJsonArtifact('ALICE_BUILD_GHOST_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/alice',
    receipt_route: '/alice/receipts/build-ghost.json',
    payload,
  });
});
