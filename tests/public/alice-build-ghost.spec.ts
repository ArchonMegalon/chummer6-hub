import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('character helper public route stays bounded and private-preview', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/alice`);
  const receiptResponse = await request.get(`${baseUrl}/alice/receipts/build-ghost.json`);

  expect(routeResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(payload.facePopStatus).toBe('Public concierge only');
  expect(payload.engineStatus).toBe('First-party compare/apply only');
  expect(payload.canonicalLane).toContain('Chummer character compare bench');
  expect(Array.isArray(payload.actions)).toBeTruthy();
  expect(payload.actions.some((item: { href?: string }) => item.href === '/alice')).toBeTruthy();
  expect(JSON.stringify(payload)).not.toContain('Build Ghost');
  expect(JSON.stringify(payload)).not.toContain('build-ghost');

  await page.goto(`${baseUrl}/alice`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Character helper' })).toBeVisible();
  await expect(page.locator('body')).toContainText('This preview is kept off the main public path');
  await expect(page.locator('body')).not.toContainText('receipt');
  await expect(page.locator('body')).not.toContainText('proof');

  writeJsonArtifact('ALICE_BUILD_GHOST_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/alice',
    receipt_route: '/alice/receipts/build-ghost.json',
    payload,
  });
});
