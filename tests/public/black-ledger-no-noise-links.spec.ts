import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger teaser and routes avoid dead links and noisy CTAs', async ({ page }) => {
  const failures: string[] = [];

  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('Build the runner. Run the night.');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toHaveCount(0);
  await expect(hero.getByRole('link')).toHaveCount(2);
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');
  await expect(hero.getByRole('link', { name: 'See what works today' })).toHaveAttribute('href', '/now');

  const playDownloads = page.locator('[data-homepage-section="play-downloads"]');
  await expect(playDownloads.getByRole('link', { name: 'Open downloads' })).toHaveAttribute('href', '/downloads');
  await expect(playDownloads.getByRole('link', { name: 'Open play shell' })).toHaveAttribute('href', '/play');
  await expect(playDownloads.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/status');

  const badLinks = await page.locator('a[href="#"], a[href=""], a[href^="javascript:void"]').evaluateAll((items) =>
    items.map((item) => (item as HTMLAnchorElement).outerHTML),
  );
  failures.push(...badLinks.map((item) => `bad link: ${item}`));

  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'domcontentloaded' });
  await expect(page).toHaveURL(/\/ledger\/map/);
  await expect(page.locator('#ledger-map')).toBeVisible();
  await expect(page.locator('[data-black-ledger-geoscape-root]').first()).toBeVisible();

  await page.goto(`${baseUrl}/ledger/factions/ashline-circle`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#ledger-faction-file')).toContainText('Ashline Circle');
  await expect(page.locator('#ledger-faction-file').getByRole('link', { name: 'Open faction video' })).toHaveAttribute('href', '/ledger/factions/ashline-circle/promo');
  await expect(page.locator('#ledger-faction-file').getByRole('link', { name: 'Promo page' })).toHaveAttribute('href', '/ledger/factions/ashline-circle/promo');

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
