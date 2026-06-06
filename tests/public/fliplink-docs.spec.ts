import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('document portal keeps Chummer as truth owner and exposes a bounded publication receipt', async ({ request, page }) => {
  const docsResponse = await request.get(`${baseUrl}/docs`);
  const guideResponse = await request.get(`${baseUrl}/docs/chummer6-quickstart`);
  const embedResponse = await request.get(`${baseUrl}/docs/embed/chummer6-quickstart`);
  const receiptResponse = await request.get(`${baseUrl}/docs/chummer6-quickstart/receipts/publication.json`);
  const pdfResponse = await request.get(`${baseUrl}/docs/chummer6-quickstart/download.pdf`);

  expect(docsResponse.status()).toBe(200);
  expect(guideResponse.status()).toBe(200);
  expect(embedResponse.status()).toBe(200);
  expect(receiptResponse.status()).toBe(200);
  expect(pdfResponse.status()).toBe(200);
  expect(pdfResponse.headers()['content-type']).toContain('application/pdf');

  const payload = await receiptResponse.json();
  expect(payload.viewerPosture).toBe('candidate_viewer_only');
  expect(payload.document.slug).toBe('chummer6-quickstart');
  expect(payload.document.sourceRepo).toBe('chummer6-design');
  expect(payload.document.sourcePath).toBe('products/chummer/public-guides/chummer6-quickstart.md');
  expect(payload.document.sourceHash).toMatch(/^[a-f0-9]{64}$/);
  expect(payload.document.pdfArtifactPath).toBe('/docs/chummer6-quickstart/download.pdf');
  expect(payload.document.pdfSha256).toMatch(/^[a-f0-9]{64}$/);
  expect(payload.document.status).toBe('approved');
  expect(payload.publication.provider).toBe('FlipLink.me');
  expect(payload.publication.publicationStatus).toBe('unpublished');
  expect(payload.receipt.embedRoute).toBe('/docs/embed/chummer6-quickstart');
  expect(payload.receipt.pdfSha256).toBe(payload.document.pdfSha256);
  expect(payload.receipt.privacyScanStatus).toBe('pass_first_party_doc_boundary');
  expect(payload.receipt.copyrightScanStatus).toBe('pass_first_party_doc_boundary');

  await page.goto(`${baseUrl}/docs/chummer6-quickstart`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Chummer6 Quickstart Guide' })).toBeVisible();
  await expect(page.locator('body')).toContainText('This document is generated and owned by Chummer.');
  await expect(page.locator('body')).toContainText('FlipLink is the optional external viewer');
  await expect(page.locator('body')).toContainText('Source hash recorded');
  await expect(page.locator('body')).toContainText('PDF fallback is current');
  await expect(page.getByRole('link', { name: 'Download PDF' })).toBeVisible();

  writeJsonArtifact('FLIPLINK_DOCS_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    docs_route: '/docs',
    guide_route: '/docs/chummer6-quickstart',
    embed_route: '/docs/embed/chummer6-quickstart',
    receipt_route: '/docs/chummer6-quickstart/receipts/publication.json',
    pdf_route: '/docs/chummer6-quickstart/download.pdf',
    payload,
  });
});
