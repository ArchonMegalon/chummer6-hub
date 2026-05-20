import { test, expect } from 'playwright/test';
import { writeMapJsonArtifact } from './black-ledger-map-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger map keeps the tactical shell interactive', async ({ page }) => {
  const started = Date.now();
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.ledger-command-map')).toBeVisible();
  const elapsedMs = Date.now() - started;

  const payload = {
    status: elapsedMs < 8000 ? 'pass' : 'fail',
    base_url: baseUrl,
    route: '/ledger/map',
    domcontentloaded_ms: elapsedMs,
  };

  // Keep the older command-map receipt and the newer globe receipt in sync.
  writeMapJsonArtifact('BLACK_LEDGER_COMMAND_MAP_PERFORMANCE.generated.json', payload);
  writeMapJsonArtifact('BLACK_LEDGER_GLOBE_PERFORMANCE.generated.json', payload);
});
