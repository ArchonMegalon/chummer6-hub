import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger becomes the homepage frontdoor without extra first-screen ctas', async ({ page }) => {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  const hero = page.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('The city is moving.');
  await expect(hero).toContainText('Join a faction, watch the pressure bulletin, and carry your runners into the Black Ledger command rail.');
  await expect(hero.locator('[data-black-ledger-geoscape-root]')).toBeVisible();
  await expect(hero.locator('canvas.black-ledger-geoscape__canvas')).toBeVisible();
  await expect(hero.locator('video.black-ledger-geoscape__video-plate')).toHaveAttribute('poster', /black-ledger-video-globe-idle-poster\.png/);
  await expect(hero.locator('video.black-ledger-geoscape__video-plate source[type="video/mp4"]')).toHaveAttribute('src', /black-ledger-video-globe-idle\.mp4/);
  const videoState = await hero.locator('[data-black-ledger-geoscape-root]').getAttribute('data-video-globe');
  const qaRenderer = await hero.locator('[data-black-ledger-geoscape-root]').getAttribute('data-qa-renderer');
  expect(videoState === 'ready' || (videoState === 'disabled' && qaRenderer === 'canvas-only')).toBeTruthy();

  const heroLinks = hero.getByRole('link');
  await expect(heroLinks).toHaveCount(2);
  await expect(hero.getByRole('link', { name: 'Open Black Ledger' })).toHaveAttribute('href', '/ledger');
  await expect(hero.getByRole('link', { name: 'Download Chummer' })).toHaveAttribute('href', '/downloads');

  writeJsonArtifact('BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/',
    cta_labels: await heroLinks.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).textContent?.trim() ?? '')),
    renderer: await hero.locator('[data-black-ledger-geoscape-root]').getAttribute('data-renderer'),
    video_globe: await hero.locator('[data-black-ledger-geoscape-root]').getAttribute('data-video-globe'),
  });
});
