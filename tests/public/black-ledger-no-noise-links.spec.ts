import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger teaser and routes avoid dead links and noisy CTAs', async ({ page }) => {
  const failures: string[] = [];

  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  const teaser = page.locator('[data-homepage-section="preview"]');
  await expect(teaser).toContainText('Turn 1 already ran. The city is moving.');
  await expect(teaser).toContainText('Emerald Sprawl is a fictional, public-safe seed world');

  const teaserLinks = teaser.locator('a');
  await expect(teaserLinks).toHaveCount(2);
  await expect(teaser.getByRole('link', { name: 'Open Black Ledger' })).toHaveAttribute('href', '/ledger');
  await expect(teaser.getByRole('link', { name: 'Replay Turn 1' })).toHaveAttribute('href', '/ledger/map?replay=turn-1');

  const badLinks = await page.locator('a[href="#"], a[href=""], a[href^="javascript:void"]').evaluateAll((items) =>
    items.map((item) => (item as HTMLAnchorElement).outerHTML),
  );
  failures.push(...badLinks.map((item) => `bad link: ${item}`));

  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('link', { name: 'Open command map' })).toHaveAttribute('href', '/ledger/map');
  await expect(page.getByRole('link', { name: 'Read dispatches' })).toHaveAttribute('href', '/ledger/dispatches');

  const ledgerBadLinks = await page.locator('a[href="#"], a[href=""], a[href^="javascript:void"]').evaluateAll((items) =>
    items.map((item) => (item as HTMLAnchorElement).outerHTML),
  );
  failures.push(...ledgerBadLinks.map((item) => `ledger bad link: ${item}`));

  writeJsonArtifact('BLACK_LEDGER_NO_NOISE_LINK_AUDIT.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    base_url: baseUrl,
    failure_count: failures.length,
    failures,
  });

  expect(failures, failures.join('\n')).toEqual([]);
});
