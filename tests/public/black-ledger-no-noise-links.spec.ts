import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger teaser and routes avoid dead links and noisy CTAs', async ({ page }) => {
  const failures: string[] = [];

  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('The city is moving.');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toBeVisible();
  await expect(hero.getByRole('link')).toHaveCount(2);
  await expect(hero.getByRole('link', { name: 'Open Black Ledger' })).toHaveAttribute('href', '/ledger');
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');

  const factions = page.locator('[data-homepage-section="factions"]');
  await expect(factions).toContainText('Six seeded houses are already pushing on the same city.');
  await expect(factions).toContainText('Open a file, read the pressure, or replay Turn 1 without touching private table state.');

  const playDownloads = page.locator('[data-homepage-section="play-downloads"]');
  await expect(playDownloads.getByRole('link', { name: 'Open downloads' })).toHaveAttribute('href', '/downloads');
  await expect(playDownloads.getByRole('link', { name: 'Replay Turn 1' })).toHaveAttribute('href', '/ledger/map?replay=turn-1');

  const badLinks = await page.locator('a[href="#"], a[href=""], a[href^="javascript:void"]').evaluateAll((items) =>
    items.map((item) => (item as HTMLAnchorElement).outerHTML),
  );
  failures.push(...badLinks.map((item) => `bad link: ${item}`));

  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('link', { name: 'Open command map' }).first()).toHaveAttribute('href', '/ledger/map#ledger-map');
  await expect(page.getByRole('link', { name: 'Read dispatches' }).first()).toHaveAttribute('href', '/ledger/dispatches');

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
