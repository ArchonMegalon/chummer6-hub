import { expect, test } from 'playwright/test';
import { completionPath, writeMarkdownArtifact } from './tests/public/ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const viewports = [
  { width: 390, height: 844 },
  { width: 412, height: 915 },
  { width: 768, height: 1024 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

test('public homepage stays readable across flagship responsive viewports', async ({ browser }) => {
  test.setTimeout(180000);
  const reportLines = [
    '# Screenshot QA Report',
    '',
    `- Generated: ${new Date().toISOString()}`,
    '',
  ];

  for (const viewport of viewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.minimal-hero h1')).toContainText('Chummer');
    await expect(page.locator('[data-homepage-section="hero"]')).toContainText('Stable');
    await expect(page.locator('[data-homepage-section="hero"]')).toContainText('Nightly');

    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    expect(overflow, `${viewport.width}x${viewport.height} has horizontal overflow`).toBeLessThanOrEqual(1);

    const screenshotName = `homepage-${viewport.width}x${viewport.height}.png`;
    await page.screenshot({ path: completionPath(screenshotName), fullPage: true });
    reportLines.push(`- ${viewport.width}x${viewport.height}: pass`);
    await page.close();
  }

  writeMarkdownArtifact('SCREENSHOT_QA_REPORT.md', reportLines.join('\n'));
});
