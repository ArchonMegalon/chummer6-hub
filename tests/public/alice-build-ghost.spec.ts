import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('character help public route stays bounded and hands private work to the signed-in bench', async ({ request, page }) => {
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
  await expect(page.locator('h1')).toContainText('Character help');
  await expect(page.locator('main')).toContainText('First-party compare/apply only');
  await expect(page.getByRole('link', { name: 'Open signed-in helper' })).toHaveAttribute('href', '/account/alice/open');
  await expect(page.locator('body')).not.toContainText('Build Ghost');
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
