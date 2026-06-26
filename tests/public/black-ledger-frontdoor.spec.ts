import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const promoVideoPath = '/media/promo/every-wonder-horizon-promo.mp4';

test('homepage stays product-first while ledger remains off the primary path', async ({ page, request }) => {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('Chummer');
  await expect(hero).toContainText('A Shadowrun character manager');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toHaveCount(0);
  await expect(page.getByText('Black Ledger')).toHaveCount(0);

  const heroLinks = hero.getByRole('link');
  const heroActionLinks = hero.locator('.minimal-actions a.button-like');
  const heroPromoLink = hero.locator('.minimal-hero__visual');
  expect(await heroLinks.count()).toBeGreaterThan(1);
  expect(await heroActionLinks.count()).toBeGreaterThan(0);
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');
  await expect(heroPromoLink).toHaveAttribute('href', promoVideoPath);

  const promoVideoUrl = new URL(promoVideoPath, `${baseUrl}/`).toString();
  const promoResponse = await request.get(promoVideoUrl);
  expect(promoResponse.ok()).toBeTruthy();
  expect((promoResponse.headers()['content-type'] ?? '').toLowerCase()).toMatch(/video|octet-stream/);

  await Promise.all([
    page.waitForURL((url) => url.toString().includes(promoVideoPath)),
    heroPromoLink.click(),
  ]);

  writeJsonArtifact('BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/',
    cta_labels: await heroActionLinks.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).textContent?.trim() ?? '')),
    promo_video_href: promoVideoPath,
    promo_video_click_verified: true,
    ledger_primary: false,
  });
});
