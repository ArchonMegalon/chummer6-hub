import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger teaser and routes avoid dead links and noisy CTAs', async ({ page }) => {
  const failures: string[] = [];

  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('Build and maintain Shadowrun characters without losing the details between sessions.');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toHaveCount(0);
  await expect(page.getByText('Black Ledger')).toHaveCount(0);
  await expect(hero.getByRole('link')).toHaveCount(2);
  await expect(hero.getByRole('link', { name: 'Stable' })).toHaveAttribute('href', '/downloads#stable');
  await expect(hero.getByRole('link', { name: 'Nightly' })).toHaveAttribute('href', '/downloads#nightly');

  const downloads = page.locator('[data-homepage-section="downloads"]');
  await expect(downloads.getByRole('link', { name: /Stable/ })).toHaveAttribute('href', '/downloads#stable');
  await expect(downloads.getByRole('link', { name: /Nightly/ })).toHaveAttribute('href', '/downloads#nightly');
  await expect(downloads.getByRole('link', { name: /Status/ })).toHaveAttribute('href', '/status');

  const badLinks = await page.locator('a[href="#"], a[href=""], a[href^="javascript:void"]').evaluateAll((items) =>
    items.map((item) => (item as HTMLAnchorElement).outerHTML),
  );
  failures.push(...badLinks.map((item) => `bad link: ${item}`));

  writeJsonArtifact('BLACK_LEDGER_GLOBE_NO_NOISE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    base_url: baseUrl,
    failure_count: failures.length,
    failures,
  });

  expect(failures, failures.join('\n')).toEqual([]);
});
