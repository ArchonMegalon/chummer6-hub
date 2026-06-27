import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger viewer network stays first-party and provider-safe', async ({ request, page }) => {
  const mapResponse = await request.get(`${baseUrl}/ledger/map`);
  const viewerReceiptResponse = await request.get(`${baseUrl}/ledger/receipts/viewer-network.json`);
  const primaryViewerResponse = await request.get(`${baseUrl}/ledger/viewers/3d-tour`, { maxRedirects: 0 });

  expect(mapResponse.status()).toBe(200);
  expect(viewerReceiptResponse.status()).toBe(200);
  expect(primaryViewerResponse.status()).toBe(302);

  const payload = await viewerReceiptResponse.json();
  expect(payload.horizon).toBe('black-ledger');
  expect(payload.status).toBe('shipped_mvp');
  expect(payload.publicBoard.flyThroughHref).toBe('/ledger/viewers/fly-through');
  expect(payload.publicBoard.viewerHref).toBe('/ledger/viewers/3d-tour');
  expect(payload.publicBoard.alternateViewerHref).toBe('/ledger/viewers/alternate-3d-tour');
  expect(payload.sharedArtifacts.publicCapabilityHealthHref).toBe(
    '/api/v1/public/horizons/capabilities?horizonId=black-ledger&artifactKindOrCapabilityId=black-ledger-viewer-network'
  );
  expect(payload.sharedArtifacts.publicRequestReceiptDetailHrefTemplate).toBe('/api/v1/public/horizons/artifact-requests/{requestId}');
  expect(payload.artifactCapability.capabilityId).toBe('black-ledger-viewer-network');
  expect(payload.artifactCapability.sourceRef).toBe('black-ledger:viewer-network');
  expect(payload.artifactCapability.quotaTracked).toBe(false);
  expect(JSON.stringify(payload)).not.toContain('Matterport');
  expect(JSON.stringify(payload)).not.toContain('3DVista');

  expect(primaryViewerResponse.headers()['location'] ?? '').toContain('my.matterport.com/show/');
  expect(primaryViewerResponse.headers()['x-horizon-artifact-request-id'] ?? '').toMatch(/^horizon-artifact-/);
  expect(primaryViewerResponse.headers()['x-horizon-artifact-request-href'] ?? '').toContain('/api/v1/public/horizons/artifact-requests/');

  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText('Optional viewer exports.');
  await expect(page.getByRole('link', { name: 'Open 3D Tour' })).toHaveAttribute('href', '/ledger/viewers/3d-tour');
  await expect(page.getByRole('link', { name: 'Open alternate 3D Tour' })).toHaveAttribute('href', '/ledger/viewers/alternate-3d-tour');
  await expect(page.locator('body')).not.toContainText('Matterport');
  await expect(page.locator('body')).not.toContainText('3DVista');

  writeJsonArtifact('BLACK_LEDGER_VIEWER_NETWORK_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map',
    viewer_receipt_route: '/ledger/receipts/viewer-network.json',
    viewer_redirect_route: '/ledger/viewers/3d-tour',
    payload,
    redirect_location: primaryViewerResponse.headers()['location'] ?? '',
  });
});
