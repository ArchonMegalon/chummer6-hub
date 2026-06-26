import { expect, test, type Browser } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

async function openPublicPage(browser: Browser, route: string) {
  const page = await browser.newPage({ baseURL: baseUrl });
  await page.goto(route, { waitUntil: 'domcontentloaded' });
  return page;
}

test('billing surfaces stay honest and origin dossier has a first-party story route', async ({ request, browser }) => {
  test.setTimeout(90000);

  const payfunnelsPage = await request.get(`${baseUrl}/account/billing/test?userId=user-a`, { maxRedirects: 0 });
  const payfunnelsProjection = await request.get(`${baseUrl}/api/billing/payfunnels/test`);
  const payfunnelsCheckout = await request.post(`${baseUrl}/account/billing/test`, {
    maxRedirects: 0,
    form: {
      userId: 'user-a',
      benefitAcknowledged: 'true',
    },
  });
  const brilliantDirectoriesPage = await request.get(`${baseUrl}/account/billing`, { maxRedirects: 0 });
  const brilliantDirectoriesPreviewPage = await request.get(`${baseUrl}/account/billing?userId=user-a&email=runner@example.com`, { maxRedirects: 0 });

  const originPage = await request.get(`${baseUrl}/origin-dossier`);
  const originStoryPage = await request.get(`${baseUrl}/docs/origin-dossier-the-name-she-chose`);
  const originReceipt = await request.get(`${baseUrl}/docs/origin-dossier-the-name-she-chose/receipts/publication.json`);
  const originPdf = await request.get(`${baseUrl}/docs/origin-dossier-the-name-she-chose/download.pdf`);
  const originBookStudioPage = await request.get(`${baseUrl}/docs/origin-book-studio`);
  const originBookStudioReceipt = await request.get(`${baseUrl}/docs/origin-book-studio/receipts/publication.json`);
  const originBookStudioPdf = await request.get(`${baseUrl}/docs/origin-book-studio/download.pdf`);
  const originVideo = await request.get(`${baseUrl}/media/horizons/origin-dossier-the-name-she-chose-20260619.mp4`);

  expect(payfunnelsPage.status()).toBe(200);
  expect(payfunnelsProjection.status()).toBe(200);
  expect(payfunnelsCheckout.status()).toBe(302);
  expect(payfunnelsCheckout.headers()['location'] || '').toContain('payfunnels');
  expect(brilliantDirectoriesPage.status()).toBe(302);
  expect(brilliantDirectoriesPage.headers()['location'] || '').toContain('/auth/google/start?next=');
  expect([302, 303, 307, 308]).toContain(brilliantDirectoriesPreviewPage.status());
  expect(brilliantDirectoriesPreviewPage.headers()['location'] || '').toContain('/auth/google/start?next=');
  expect(brilliantDirectoriesPreviewPage.headers()['location'] || '').toContain('%2Faccount%2Fbilling');
  expect(brilliantDirectoriesPreviewPage.status()).not.toBe(500);

  expect(originPage.status()).toBe(200);
  expect(originStoryPage.status()).toBe(200);
  expect(originReceipt.status()).toBe(200);
  expect(originPdf.status()).toBe(200);
  expect(originPdf.headers()['content-type']).toContain('application/pdf');
  expect(originBookStudioPage.status()).toBe(200);
  expect(originBookStudioReceipt.status()).toBe(200);
  expect(originBookStudioPdf.status()).toBe(200);
  expect(originBookStudioPdf.headers()['content-type']).toContain('application/pdf');
  expect(originVideo.status()).toBe(200);

  const payfunnelsText = await payfunnelsPage.text();
  expect(payfunnelsText).toContain('$1 Billing Test');
  expect(payfunnelsText).toContain('unlocks no benefits');
  expect(payfunnelsText).not.toContain('Premium');
  expect(payfunnelsText).not.toContain('Upgrade');

  const brilliantDirectoriesText = await brilliantDirectoriesPreviewPage.text();
  expect(brilliantDirectoriesText).not.toContain('Books this month:');
  expect(brilliantDirectoriesText).not.toContain('Account attached: user-a');
  expect(brilliantDirectoriesText).not.toContain('external billing checkout');
  expect(brilliantDirectoriesText).not.toContain('external billing page');
  expect(brilliantDirectoriesText).not.toContain('hosted billing route');
  expect(brilliantDirectoriesText).not.toContain('Premium');
  expect(brilliantDirectoriesText).not.toContain('Upgrade');

  const originPayload = await originReceipt.json();
  expect(originPayload.document.slug).toBe('origin-dossier-the-name-she-chose');
  expect(originPayload.document.sourcePath).toBe('products/chummer/horizons/origin-dossier.md');
  expect(originPayload.receipt.embedRoute).toBe('/docs/embed/origin-dossier-the-name-she-chose');
  expect(originPayload.viewerPosture).toBe('operator_managed_viewer_optional');

  const originBookStudioPayload = await originBookStudioReceipt.json();
  expect(originBookStudioPayload.document.slug).toBe('origin-book-studio');
  expect(originBookStudioPayload.document.sourcePath).toBe('products/chummer/ORIGIN_BOOK_STUDIO.md');
  expect(originBookStudioPayload.receipt.embedRoute).toBe('/docs/embed/origin-book-studio');
  expect(originBookStudioPayload.viewerPosture).toBe('operator_managed_viewer_optional');

  const dossierPage = await openPublicPage(browser, '/origin-dossier');
  await expect(dossierPage.getByRole('heading', { name: 'Origin Dossier' })).toBeVisible();
  await expect(dossierPage.locator('body')).toContainText('story packet');
  await expect(dossierPage.locator('body')).toContainText('The sheet stays authoritative');
  await expect(dossierPage.getByRole('link', { name: 'Open the story booklet' })).toBeVisible();
  await expect(dossierPage.getByRole('link', { name: 'Read the book-studio design' })).toBeVisible();
  await dossierPage.close();

  const storyPage = await openPublicPage(browser, '/docs/origin-dossier-the-name-she-chose');
  await expect(storyPage.getByRole('heading', { name: 'Origin Dossier: The Name She Chose' })).toBeVisible();
  await expect(storyPage.locator('body')).toContainText('approved story packet');
  await expect(storyPage.locator('body')).toContainText('Fallback PDF is current');
  await expect(storyPage.getByRole('link', { name: 'Download PDF' })).toBeVisible();
  await storyPage.close();

  const bookStudioPage = await openPublicPage(browser, '/docs/origin-book-studio');
  await expect(bookStudioPage.getByRole('heading', { name: 'Origin Book Studio' })).toBeVisible();
  await expect(bookStudioPage.locator('body')).toContainText('first-party route');
  await expect(bookStudioPage.locator('body')).toContainText('Fallback PDF is current');
  await expect(bookStudioPage.getByRole('link', { name: 'Download PDF' })).toBeVisible();
  await bookStudioPage.close();

  writeJsonArtifact('BILLING_ORIGIN_DOSSIER_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    payfunnels_page_status: payfunnelsPage.status(),
    payfunnels_projection_status: payfunnelsProjection.status(),
    payfunnels_checkout_status: payfunnelsCheckout.status(),
    brilliant_directories_status: brilliantDirectoriesPage.status(),
    brilliant_directories_preview_status: brilliantDirectoriesPreviewPage.status(),
    origin_page_status: originPage.status(),
    origin_story_page_status: originStoryPage.status(),
    origin_receipt_status: originReceipt.status(),
    origin_pdf_status: originPdf.status(),
    origin_book_studio_page_status: originBookStudioPage.status(),
    origin_book_studio_receipt_status: originBookStudioReceipt.status(),
    origin_book_studio_pdf_status: originBookStudioPdf.status(),
    origin_video_status: originVideo.status(),
    origin_story_slug: originPayload.document.slug,
    origin_book_studio_slug: originBookStudioPayload.document.slug,
  });
});
