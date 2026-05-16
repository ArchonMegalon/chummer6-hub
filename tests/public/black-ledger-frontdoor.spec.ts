import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger becomes the homepage frontdoor without extra first-screen ctas', async ({ page }) => {
  await page.goto(baseUrl, { waitUntil: 'networkidle' });

  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('The city is moving.');
  await expect(hero).toContainText('Track faction pressure, package heat, dispatches, and closeouts from the Black Ledger.');

  const heroLinks = hero.getByRole('link');
  await expect(heroLinks).toHaveCount(2);
  await expect(hero.getByRole('link', { name: 'Enter Black Ledger' })).toHaveAttribute('href', '/ledger');
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');

  writeJsonArtifact('BLACK_LEDGER_FRONTDOOR_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/',
    cta_labels: await heroLinks.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).textContent?.trim() ?? '')),
  });
});
