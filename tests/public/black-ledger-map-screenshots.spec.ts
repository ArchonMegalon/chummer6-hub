import { test, expect } from 'playwright/test';
import { writeMapMarkdownArtifact, mapCompletionPath } from './black-ledger-map-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const viewports = [
  { width: 390, height: 844 },
  { width: 412, height: 915 },
  { width: 768, height: 1024 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

for (const viewport of viewports) {
  test(`black ledger map screenshot ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.ledger-command-map')).toBeVisible();
    await page.screenshot({ path: mapCompletionPath(`black-ledger-map-${viewport.width}x${viewport.height}.png`), fullPage: true });
  });
}

test.afterAll(async () => {
  writeMapMarkdownArtifact(
    'BLACK_LEDGER_COMMAND_MAP_SCREENSHOT_REPORT.md',
    [
      '# Black Ledger Command Map Screenshots',
      '',
      ...viewports.map((viewport) => `- ${viewport.width}x${viewport.height}: captured`),
    ].join('\n'));
});
