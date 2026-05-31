import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('homepage and ledger routes use the globe as the primary render surface', async ({ page }) => {
  const results: Array<Record<string, unknown>> = [];
  for (const route of ['/', '/ledger', '/ledger/map']) {
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });
    const root = page.locator('[data-black-ledger-geoscape-root]').first();
    await expect(root).toHaveAttribute('data-ready', 'true');
    await expect(root.locator('canvas.black-ledger-geoscape__canvas')).toBeVisible();
    await expect(root.locator('video.black-ledger-geoscape__video-plate')).toHaveAttribute('poster', /black-ledger-video-globe-idle-poster\.png/);
    await expect(root.locator('video.black-ledger-geoscape__video-plate source[type="video/mp4"]')).toHaveAttribute('src', /black-ledger-video-globe-idle\.mp4/);
    const box = await root.boundingBox();
    results.push({
      route,
      renderer: await root.getAttribute('data-renderer'),
      video_globe: await root.getAttribute('data-video-globe'),
      ready: await root.getAttribute('data-ready'),
      height: box?.height ?? 0,
    });
  }

  writeJsonArtifact('BLACK_LEDGER_GLOBE_RENDER.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    results,
  });
});
