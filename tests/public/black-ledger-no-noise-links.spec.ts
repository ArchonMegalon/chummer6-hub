import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger teaser and routes avoid dead links and noisy CTAs', async ({ page }) => {
  const failures: string[] = [];

  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('The city is moving.');
  await expect(hero.locator('[data-black-ledger-geoscape-root][data-ready="true"]')).toBeVisible();
  await expect(hero.getByRole('link')).toHaveCount(2);
  await expect(hero.getByRole('link', { name: 'Enter Black Ledger' })).toHaveAttribute('href', '/ledger');
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');
  await expect(page.locator('[data-homepage-section]')).toHaveCount(5);

  const playDownloads = page.locator('[data-homepage-section="play-downloads"]');
  await expect(playDownloads).toContainText('Mobile play shell preview');
  await expect(playDownloads).toContainText('Proof, route health, and verification notes stay on Status');

  const badLinks = await page.locator('a[href="#"], a[href=""], a[href^="javascript:void"]').evaluateAll((items) =>
    items.map((item) => (item as HTMLAnchorElement).outerHTML),
  );
  failures.push(...badLinks.map((item) => `bad link: ${item}`));

  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('link', { name: 'Open command map' })).toHaveAttribute('href', '/ledger/map#ledger-map');
  await expect(page.getByRole('link', { name: 'Read dispatches' })).toHaveAttribute('href', '/ledger/dispatches');

  await page.goto(`${baseUrl}/ledger/factions/ashline-circle`, { waitUntil: 'networkidle' });
  await expect(page.locator('#ledger-faction-file')).toContainText('Ashline Circle');
  await expect(page.locator('#ledger-faction-file').getByRole('link', { name: 'Open faction video' })).toHaveAttribute('href', '/ledger/factions/ashline-circle/promo');
  await expect(page.locator('#ledger-faction-file').getByRole('link', { name: /Join a faction|Open onboarding/ })).toBeVisible();

  const ledgerBadLinks = await page.locator('a[href="#"], a[href=""], a[href^="javascript:void"]').evaluateAll((items) =>
    items.map((item) => (item as HTMLAnchorElement).outerHTML),
  );
  failures.push(...ledgerBadLinks.map((item) => `ledger bad link: ${item}`));

  writeJsonArtifact('BLACK_LEDGER_GLOBE_NO_NOISE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    base_url: baseUrl,
    failure_count: failures.length,
    failures,
  });

  expect(failures, failures.join('\n')).toEqual([]);
});
