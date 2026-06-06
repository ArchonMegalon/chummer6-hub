import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

test('document portal stays readable on desktop and mobile with a visible fallback path', async ({ page }) => {
  const results: Array<Record<string, unknown>> = [];

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`${baseUrl}/docs/chummer6-quickstart`, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: 'Chummer6 Quickstart Guide' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Download PDF' })).toBeVisible();
    await expect(page.locator('body')).toContainText('This document is generated and owned by Chummer.');
    await expect(page.locator('body')).toContainText('External viewer remains optional');

    results.push({
      viewport: viewport.name,
      width: viewport.width,
      height: viewport.height,
      headingVisible: await page.getByRole('heading', { name: 'Chummer6 Quickstart Guide' }).isVisible(),
      pdfLinkVisible: await page.getByRole('link', { name: 'Download PDF' }).isVisible(),
      boundaryVisible: await page.locator('body').textContent(),
    });
  }

  writeJsonArtifact('FLIPLINK_DOCS_RESPONSIVE_QA.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/docs/chummer6-quickstart',
    fallback_pdf_route: '/docs/chummer6-quickstart/download.pdf',
    results,
  });
});
