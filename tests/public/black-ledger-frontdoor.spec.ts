import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('homepage stays product-first while ledger remains off the primary path', async ({ page }) => {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('Chummer');
  await expect(hero).toContainText('Build and maintain Shadowrun characters without losing the details between sessions.');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toHaveCount(0);
  await expect(page.getByText('Black Ledger')).toHaveCount(0);

  const heroLinks = hero.getByRole('link');
  await expect(heroLinks).toHaveCount(2);
  await expect(hero.getByRole('link', { name: 'Stable' })).toHaveAttribute('href', '/downloads#stable');
  await expect(hero.getByRole('link', { name: 'Nightly' })).toHaveAttribute('href', '/downloads#nightly');

  writeJsonArtifact('BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/',
    cta_labels: await heroLinks.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).textContent?.trim() ?? '')),
    ledger_primary: false,
  });
});
