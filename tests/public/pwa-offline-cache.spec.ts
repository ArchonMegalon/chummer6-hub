import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('service worker caches the public shell strongly enough for offline mobile replay fallback', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'domcontentloaded' });

  await page.evaluate(async () => {
    if ('serviceWorker' in navigator) {
      await navigator.serviceWorker.ready;
    }
  });

  await context.setOffline(true);
  await page.goto(`${baseUrl}/mobile`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText('Installable app shell live');
  await expect(page.locator('body')).toContainText('Offline and reconnect lane cached');
  await expect(page.locator('body')).not.toContainText('installability proof pending');

  writeJsonArtifact('PWA_OFFLINE_CACHE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/mobile',
    offline_reload: 'pass',
  });
});
