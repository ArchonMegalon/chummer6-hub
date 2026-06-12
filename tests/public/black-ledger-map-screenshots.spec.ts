import { test, expect } from 'playwright/test';
import { completionPath, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const gotoOptions = { waitUntil: 'domcontentloaded' as const, timeout: 45000 };
const readyTimeout = 30000;
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
    test.setTimeout(90000);
    await page.setViewportSize(viewport);
    await page.goto(`${baseUrl}/ledger/map`, gotoOptions);

    const commandMapGeoscape = page.locator(
      '.ledger-command-map__globe .ledger-flagship__geoscape[data-black-ledger-geoscape-root]'
    );
    await expect(commandMapGeoscape).toHaveAttribute('data-ready', 'true', { timeout: readyTimeout });
    await commandMapGeoscape.scrollIntoViewIfNeeded();
    await expect(commandMapGeoscape).toBeVisible();
    await page.screenshot({ path: completionPath(`black-ledger-map-${viewport.width}x${viewport.height}.png`), fullPage: true });
  });
}

test.afterAll(async () => {
  writeMarkdownArtifact(
    'BLACK_LEDGER_MAP_SCREENSHOT_REPORT.md',
    [
      '# Black Ledger Map Screenshots',
      '',
      ...viewports.map((viewport) => `- ${viewport.width}x${viewport.height}: captured`),
    ].join('\n'));
});
