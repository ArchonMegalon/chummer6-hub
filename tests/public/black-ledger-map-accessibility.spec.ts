import { test, expect } from 'playwright/test';
import { writeMapJsonArtifact } from './black-ledger-map-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger map keeps keyboard and fallback access visible', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });

  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toBeVisible();
  await expect(page.locator('#district-rust-bazaar')).toBeVisible();
  expect(await page.locator('.ledger-world-shell__districts .route-choice-card').count()).toBeGreaterThan(3);

  writeMapJsonArtifact('BLACK_LEDGER_COMMAND_MAP_ACCESSIBILITY.generated.json', {
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map',
    list_fallback_cards: await page.locator('.ledger-world-shell__districts .route-choice-card').count(),
  });
});
