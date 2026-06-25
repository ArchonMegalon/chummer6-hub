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
  const originVideo = await request.get(`${baseUrl}/media/horizons/origin-dossier-the-name-she-chose-20260619.mp4`);

  expect(payfunnelsPage.status()).toBe(200);
  expect(payfunnelsProjection.status()).toBe(200);
  expect(payfunnelsCheckout.status()).toBe(302);
  expect(payfunnelsCheckout.headers()['location'] || '').toContain('payfunnels');
  expect(brilliantDirectoriesPage.status()).toBe(302);
  expect(brilliantDirectoriesPage.headers()['location'] || '').toContain('/auth/google/start?next=');
  expect([200, 503]).toContain(brilliantDirectoriesPreviewPage.status());
  expect(brilliantDirectoriesPreviewPage.status()).not.toBe(500);

  expect(originPage.status()).toBe(200);
  expect(originStoryPage.status()).toBe(200);
  expect(originReceipt.status()).toBe(200);
  expect(originPdf.status()).toBe(200);
  expect(originPdf.headers()['content-type']).toContain('application/pdf');
  expect(originVideo.status()).toBe(200);

  const payfunnelsText = await payfunnelsPage.text();
  expect(payfunnelsText).toContain('$1 Billing Test');
  expect(payfunnelsText).toContain('unlocks no benefits');
  expect(payfunnelsText).not.toContain('Premium');
  expect(payfunnelsText).not.toContain('Upgrade');

  const brilliantDirectoriesText = await brilliantDirectoriesPreviewPage.text();
  if (brilliantDirectoriesPreviewPage.status() === 200) {
    expect(brilliantDirectoriesText).toContain('Free and Supporter have the same Chummer app access.');
    expect(brilliantDirectoriesText).toContain('Supporter');
    expect(brilliantDirectoriesText).toContain('Same Chummer app. Supporter helps cover the work.');
    expect(brilliantDirectoriesText).toContain('Origin books: Free gets 1 per month. Supporter gets 2.');
    expect(brilliantDirectoriesText).toContain('Supporter keeps the same app access and raises the Origin Book allowance to 2 per month.');
    expect(brilliantDirectoriesText).toContain('1 Origin Book per month');
    expect(brilliantDirectoriesText).toContain('2 Origin Books per month');
    expect(brilliantDirectoriesText).toContain('This account:');
    expect(brilliantDirectoriesText).not.toContain('external billing checkout');
    expect(brilliantDirectoriesText).not.toContain('external billing page');
    expect(brilliantDirectoriesText).not.toContain('hosted billing route');
    expect(brilliantDirectoriesText).not.toContain('Premium');
    expect(brilliantDirectoriesText).not.toContain('Upgrade');
  }

  const originPayload = await originReceipt.json();
  expect(originPayload.document.slug).toBe('origin-dossier-the-name-she-chose');
  expect(originPayload.document.sourcePath).toBe('products/chummer/horizons/origin-dossier.md');
  expect(originPayload.receipt.embedRoute).toBe('/docs/embed/origin-dossier-the-name-she-chose');
  expect(originPayload.viewerPosture).toBe('operator_managed_viewer_optional');

  const dossierPage = await openPublicPage(browser, '/origin-dossier');
  await expect(dossierPage.getByRole('heading', { name: 'Origin Dossier' })).toBeVisible();
  await expect(dossierPage.locator('body')).toContainText('story packet');
  await expect(dossierPage.locator('body')).toContainText('The sheet stays authoritative');
  await expect(dossierPage.getByRole('link', { name: 'Open the story booklet' })).toBeVisible();
  await dossierPage.close();

  const storyPage = await openPublicPage(browser, '/docs/origin-dossier-the-name-she-chose');
  await expect(storyPage.getByRole('heading', { name: 'Origin Dossier: The Name She Chose' })).toBeVisible();
  await expect(storyPage.locator('body')).toContainText('approved story packet');
  await expect(storyPage.locator('body')).toContainText('Fallback PDF is current');
  await expect(storyPage.getByRole('link', { name: 'Download PDF' })).toBeVisible();
  await storyPage.close();

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
    origin_video_status: originVideo.status(),
    origin_story_slug: originPayload.document.slug,
  });
});
