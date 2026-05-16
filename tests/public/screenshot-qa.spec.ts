import { expect, test } from 'playwright/test';
import { completionPath, writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = 'https://chummer.run';
const viewports = [
  { width: 390, height: 844 },
  { width: 412, height: 915 },
  { width: 768, height: 1024 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

test('public homepage screenshot QA stays readable across flagship viewports', async ({ browser }) => {
  test.setTimeout(180000);
  const results: Array<Record<string, unknown>> = [];
  const failures: string[] = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport });
    await page.goto(baseUrl, { waitUntil: 'networkidle' });

    const heroTitle = page.locator('.launch-hero__title');
    const primaryCta = page.locator('.launch-hero__actions a.button-like').first();
    const footer = page.locator('[data-homepage-section="trust-footer"]');
    const preview = page.locator('[data-homepage-section="preview"]');
    const sidebar = page.locator('.site-sidebar');

    await expect(heroTitle).toContainText('Build the runner. Run the table. Keep the ledger honest.');
    await expect(primaryCta).toContainText('Open downloads');
    await expect(preview).toContainText('Black Ledger');
    await expect(preview).toContainText('Karma Forge');
    await expect(footer).toBeVisible();

    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    if (overflow > 1) {
      failures.push(`${viewport.width}x${viewport.height}: horizontal overflow ${overflow}px`);
    }

    const heroBox = await heroTitle.boundingBox();
    const ctaBox = await primaryCta.boundingBox();
    if (!heroBox || !ctaBox) {
      failures.push(`${viewport.width}x${viewport.height}: hero title or primary CTA is not visible`);
    }

    const screenshotName = `homepage-${viewport.width}x${viewport.height}.png`;
    await page.screenshot({ path: completionPath(screenshotName), fullPage: true });

    results.push({
      viewport: `${viewport.width}x${viewport.height}`,
      overflow_px: overflow,
      hero_visible: !!heroBox,
      cta_visible: !!ctaBox,
      footer_visible: await footer.isVisible(),
      sidebar_visible: await sidebar.isVisible(),
      screenshot: screenshotName,
      status: overflow <= 1 && heroBox && ctaBox ? 'pass' : 'fail',
    });

    await page.close();
  }

  writeJsonArtifact('SCREENSHOT_QA.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    failures,
    results,
  });

  const lines = [
    '# Screenshot QA Report',
    '',
    `- Generated: ${new Date().toISOString()}`,
    '',
    ...results.map((result) => `- ${result.viewport}: ${result.status}`),
  ];
  if (failures.length > 0) {
    lines.push('', '## Failures', '', ...failures.map((failure) => `- ${failure}`));
  }
  writeMarkdownArtifact('SCREENSHOT_QA_REPORT.md', lines.join('\n'));

  expect(failures, failures.join('\n')).toEqual([]);
});
