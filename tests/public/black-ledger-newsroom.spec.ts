import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger newsroom routes issue public-safe receipts and protected media urls', async ({ request, page }) => {
  const [newsreelJson, newsroomWatch] = await Promise.all([
    request.get(`${baseUrl}/ledger/turns/1/newsreel.json`),
    request.get(`${baseUrl}/ledger/newsroom/turn-1-newsreel`),
  ]);

  expect(newsreelJson.status()).toBe(200);
  expect(newsroomWatch.status()).toBe(200);

  const payload = await newsreelJson.json();
  expect(payload.artifactCapability.capabilityId).toBe('black-ledger-newsroom');
  expect(payload.artifactCapability.artifactKind).toBe('newsroom_bulletin');
  expect(payload.artifactCapability.sourceRef).toBe('black-ledger:turn-1:newsroom');

  const protectedVideoUrl = new URL(payload.broadcast.videoMp4Href, baseUrl);
  expect(protectedVideoUrl.searchParams.get('artifactAccess')).toBeTruthy();
  const rawVideoResponse = await request.get(`${protectedVideoUrl.origin}${protectedVideoUrl.pathname}`);
  expect(rawVideoResponse.status()).toBe(404);

  await page.goto(`${baseUrl}/ledger/newsroom/turn-1-newsreel`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText('Black Ledger Newsroom');
  await expect(page.locator('body')).toContainText('Transcript');
  await expect(page.locator('body')).toContainText('Details');

  writeJsonArtifact('BLACK_LEDGER_NEWSROOM_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    artifact_capability: payload.artifactCapability,
    protected_video_href: payload.broadcast.videoMp4Href,
  });
});
