import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger teaser and routes avoid dead links and noisy CTAs', async ({ page }) => {
  const failures: string[] = [];

  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('A Shadowrun character manager');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toHaveCount(0);
  await expect(page.getByText('Black Ledger')).toHaveCount(0);
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');
  await expect(hero.getByRole('link', { name: 'Sign in first' })).toHaveAttribute('href', '/login?next=%2Faccount%2Faccess');
  await expect(hero.getByRole('link', { name: 'Help' })).toHaveAttribute('href', '/help');
  await expect(hero.getByRole('link', { name: 'Status' })).toHaveCount(0);
  await expect(hero.locator('.minimal-hero__visual--preview')).toContainText('Desktop build. Mobile play packet.');
  await expect(hero.locator('.minimal-hero__visual--preview')).toContainText('Keep quick rolls and odds within reach.');
  await expect(hero.locator('.minimal-hero__visual--screenshot')).toHaveCount(0);
  const heroLinkCount = await hero.getByRole('link').count();
  expect(heroLinkCount).toBeGreaterThanOrEqual(3);

  await expect(page.locator('[data-homepage-section="downloads"]')).toHaveCount(0);

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
