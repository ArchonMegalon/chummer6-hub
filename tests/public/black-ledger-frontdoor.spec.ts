import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
test('homepage stays product-first while ledger remains off the primary path', async ({ page }) => {
  test.setTimeout(60000);
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('Chummer');
  await expect(hero).toContainText('A Shadowrun character manager');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toHaveCount(0);
  await expect(page.getByText('Black Ledger')).toHaveCount(0);

  const heroLinks = hero.getByRole('link');
  const heroActionLinks = hero.locator('.minimal-actions a.button-like');
  expect(await heroLinks.count()).toBeGreaterThan(1);
  expect(await heroActionLinks.count()).toBeGreaterThan(0);
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');
  await expect(hero.locator('.minimal-hero__visual--preview')).toContainText('Desktop build. Mobile play packet.');
  await expect(hero.locator('.minimal-hero__visual--preview')).toContainText('Track health, ammo, inventory, and modifiers.');
  await expect(hero.locator('.minimal-hero__visual--screenshot')).toHaveCount(0);
  await expect(hero.locator('.minimal-runner-rail')).toHaveCount(0);
  const openMenu = hero.locator('.minimal-open-chummer');
  const openMenuSummary = openMenu.locator('summary');
  await expect(openMenuSummary.locator('.site-account-menu__label')).toContainText('Open Chummer');
  await openMenuSummary.click();
  await expect(openMenu).toHaveAttribute('open', '');
  await expect(openMenu.locator('button.site-open-chummer-menu__button', { hasText: 'Build' })).toBeDisabled();
  await expect(openMenu.locator('button.site-open-chummer-menu__button', { hasText: 'Play' })).toHaveCount(0);
  await expect(openMenu.locator('.site-open-chummer-menu__button[href="/build"]')).toHaveCount(0);
  await expect(openMenu.locator('.site-open-chummer-menu__button[href="/mobile/player"]', { hasText: 'Play' })).toHaveCount(1);
  await expect(openMenu.locator('.site-open-chummer-menu__button[href="/play"]')).toHaveCount(0);
  await expect(openMenu.getByRole('link', { name: 'Sign in first' })).toHaveAttribute('href', '/login?next=%2Faccount%2Faccess');

  writeJsonArtifact('BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json', {
    contractName: 'chummer.black_ledger_globe_frontdoor.v1',
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/',
    cta_labels: await heroActionLinks.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).textContent?.trim() ?? '')),
    open_menu_targets: ['/mobile/player', '/login?next=%2Faccount%2Faccess'],
    gated_targets: ['Build'],
    public_targets: ['Play'],
    ledger_primary: false,
  });
});
