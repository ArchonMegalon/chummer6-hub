import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger newsreel packet stays route-backed and professional', async ({ request, page }) => {
  const turnPage = await request.get(`${baseUrl}/ledger/turns/1`);
  const newsreel = await request.get(`${baseUrl}/ledger/turns/1/newsreel.json`);
  const payload = await newsreel.json();

  expect(turnPage.status()).toBe(200);
  expect(newsreel.status()).toBe(200);
  expect(payload.fromTurn).toBe(0);
  expect(payload.toTurn).toBe(1);
  expect(payload.transitionLabel).toBe('Turn 0 -> Turn 1');
  expect(payload.transitionNarrative).toContain('Turn 0');
  expect(payload.newsreelLead).toContain('Turn 1');
  expect(Array.isArray(payload.newsreelBullets)).toBeTruthy();
  expect(payload.newsreelBullets.length).toBeGreaterThan(0);
  expect(Array.isArray(payload.validationChecks)).toBeTruthy();
  expect(payload.broadcast).toBeTruthy();
  expect(payload.broadcast.videoMp4Href).toContain('/media/ledger/newsreels/turn-1-newsreel.mp4');
  expect(payload.broadcast.captionsHref).toContain('.vtt');

  await page.goto(`${baseUrl}/ledger/turns/1`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText('command map');
  await expect(page.locator('#newsreel-player video')).toBeVisible();
  await expect(page.locator('body')).toContainText(/(First-party|Chummer) (anchor package|synthetic score bed with ducked narration)/i);
  await expect(page.locator('body')).toContainText('Turn 0 -> Turn 1');
  await expect(page.getByLabel('Black Ledger actions').getByRole('link', { name: 'Latest bulletin' })).toHaveAttribute('href', '/ledger/turns/1/digest');

  writeJsonArtifact('BLACK_LEDGER_NEWSREEL_PARITY.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/turns/1/newsreel.json',
    payload,
  });
});
