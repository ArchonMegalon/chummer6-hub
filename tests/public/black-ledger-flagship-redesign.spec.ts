import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger route opens as a command deck without clipped flagship copy', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'domcontentloaded' });

  const deck = page.locator('[data-ledger-redesign="command-deck"]');
  const title = deck.locator('h1.page-title');
  const globe = deck.locator('[data-black-ledger-geoscape-root]');
  const actions = deck.locator('.ledger-flagship__actions a');

  await expect(deck).toBeVisible();
  await expect(globe).toHaveAttribute('data-ready', 'true');
  await expect(actions).toHaveCount(4);
  const actionHrefs = await actions.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).getAttribute('href') ?? ''));
  expect(actionHrefs).toContain('/ledger/map#ledger-map');
  expect(actionHrefs).toContain('/ledger/dispatches');

  const fit = await title.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const parentBounds = element.parentElement?.getBoundingClientRect();
    return {
      titleWidth: bounds.width,
      parentWidth: parentBounds?.width ?? 0,
      titleRight: bounds.right,
      parentRight: parentBounds?.right ?? 0,
      lineHeight: Number.parseFloat(getComputedStyle(element).lineHeight),
      height: bounds.height,
    };
  });

  expect(fit.titleWidth).toBeLessThanOrEqual(fit.parentWidth);
  expect(fit.titleRight).toBeLessThanOrEqual(fit.parentRight + 1);
  expect(fit.height / fit.lineHeight).toBeLessThanOrEqual(4.2);

  writeJsonArtifact('BLACK_LEDGER_FLAGSHIP_REDESIGN.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    desktop_title_fit: fit,
  });
});

test('black ledger mobile first screen reaches the globe', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'domcontentloaded' });

  const globe = page.locator('[data-ledger-redesign="command-deck"] [data-black-ledger-geoscape-root]').first();
  await expect(globe).toHaveAttribute('data-ready', 'true');

  const box = await globe.boundingBox();
  expect(box?.y ?? Number.POSITIVE_INFINITY).toBeLessThan(844);
  expect(box?.height ?? 0).toBeGreaterThan(460);
});
