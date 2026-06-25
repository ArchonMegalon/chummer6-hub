import { expect, test } from 'playwright/test';
import { writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('public surfaces stay minimal and first-task oriented', async ({ browser }) => {
  test.setTimeout(180000);
  const failures: string[] = [];
  const results: Array<Record<string, unknown>> = [];

  const desktop = await browser.newPage({ baseURL: baseUrl, viewport: { width: 1366, height: 768 } });

  await desktop.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await expect(desktop.locator('.site-nav')).toHaveCount(0);
  await expect(desktop.locator('[data-nav-toggle]')).toHaveCount(0);
  await expect(desktop.locator('.minimal-hero h1')).toContainText('Chummer');
  await expect(desktop.locator('.minimal-hero__lead')).toContainText('A Shadowrun character manager');
  const heroActions = await desktop.locator('.minimal-hero .minimal-actions a.button-like').allTextContents();
  if (heroActions.map((text) => text.trim()).join('|') !== 'Download Chummer') {
    failures.push(`homepage: expected one Download Chummer hero action, found ${heroActions.join(', ')}`);
  }
  const heroImage = desktop.locator('.minimal-hero__visual img');
  const heroMediaLink = desktop.locator('.minimal-hero__visual[href="/media/promo/chummer6-flagship-promo.mp4"]');
  await expect(heroImage).toBeVisible();
  await expect(heroMediaLink).toHaveCount(1);
  const heroImageLoaded = await heroImage.evaluate((node) => {
    const image = node as HTMLImageElement;
    return image.complete && (image.naturalWidth > 0 || image.naturalHeight > 0);
  });
  if (!heroImageLoaded) {
    failures.push('homepage: hero image did not load');
  }
  await expect(desktop.locator('[data-homepage-section="workflow"]')).toHaveCount(0);
  await expect(desktop.locator('[data-homepage-section="downloads"]')).toHaveCount(0);
  await expect(desktop.locator('.minimal-inline-links')).toContainText('Help');
  await expect(desktop.locator('.minimal-inline-links')).not.toContainText('Participate');
  await expect(desktop.locator('.site-nav')).toHaveCount(0);
  const homepageText = await desktop.locator('[data-homepage-section="hero"]').innerText();
  const homepageManifestResponse = await desktop.request.get(`${baseUrl}/downloads/RELEASE_CHANNEL.generated.json`);
  expect(homepageManifestResponse.ok()).toBeTruthy();
  const homepageManifest = await homepageManifestResponse.json();
  const homepagePromotedPlatforms = Array.from(
    new Set(
      ((homepageManifest.artifacts || []) as Array<Record<string, unknown>>)
        .map((artifact) => String(artifact.platform || artifact.platformId || '').toLowerCase())
        .filter((platform) => platform === 'windows' || platform === 'linux'),
    ),
  );
  if (!homepagePromotedPlatforms.includes('linux') && homepageText.includes('Windows and Linux')) {
    failures.push('homepage: claims Linux availability while the release manifest does not promote Linux');
  }
  const heroBox = await desktop.locator('[data-homepage-section="hero"]').boundingBox();
  if (!heroBox || heroBox.y + heroBox.height > 768) {
    failures.push('homepage: hero still extends below the desktop viewport');
  }
  results.push({
    surface: 'home',
    inline_nav_visible: false,
    hero_image_loaded: heroImageLoaded,
    promo_video_entry: '/media/promo/chummer6-flagship-promo.mp4',
    first_viewport_fits: !!heroBox && heroBox.y + heroBox.height <= 768,
    promoted_platforms: homepagePromotedPlatforms,
  });

  await desktop.goto(`${baseUrl}/downloads`, { waitUntil: 'domcontentloaded' });
  const manifestResponse = await desktop.request.get(`${baseUrl}/downloads/RELEASE_CHANNEL.generated.json`);
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  const promotedPlatforms = Array.from(
    new Set(
      ((manifest.artifacts || []) as Array<Record<string, unknown>>)
        .map((artifact) => String(artifact.platform || artifact.platformId || '').toLowerCase())
        .filter((platform) => platform === 'windows' || platform === 'linux'),
    ),
  );
  const stableLane = desktop.locator('#stable');
  const nightlyLane = desktop.locator('#nightly');
  await expect(stableLane).toBeVisible();
  await expect(nightlyLane).toBeVisible();
  for (const platform of promotedPlatforms) {
    const label = platform === 'windows' ? 'Windows' : 'Linux';
    await expect(stableLane.getByRole('link', { name: label })).toBeVisible();
    await expect(nightlyLane.getByRole('link', { name: label })).toBeVisible();
  }
  const downloadsText = await desktop.locator('body').innerText();
  if (!promotedPlatforms.includes('linux') && downloadsText.includes('Windows and Linux installers.')) {
    failures.push('downloads: claims Linux installers while the release manifest does not promote Linux');
  }
  for (const forbidden of ['Signed-in download', 'portable', 'recommended download', 'proof', 'receipt']) {
    if (downloadsText.toLowerCase().includes(forbidden.toLowerCase())) {
      failures.push(`downloads: contains retired copy "${forbidden}"`);
    }
  }
  results.push({ surface: 'downloads', stable_visible: true, nightly_visible: true, promoted_platforms: promotedPlatforms });

  await desktop.goto(`${baseUrl}/status`, { waitUntil: 'domcontentloaded' });
  const decisionSurface = desktop.locator('[data-status-surface="decision-surface"]');
  const decisionCards = decisionSurface.locator('.route-choice-card');
  const nextActions = decisionSurface.locator('.minimal-actions a.button-like');
  await expect(decisionSurface).toBeVisible();
  await expect(decisionSurface).toContainText('Release');
  await expect(decisionSurface).toContainText('Open downloads');
  const cardCount = await decisionCards.count();
  if (cardCount !== 1) {
    failures.push(`status: expected exactly 1 decision card, found ${cardCount}`);
  }
  const nextActionCount = await nextActions.count();
  if (nextActionCount !== 3) {
    failures.push(`status: expected exactly 3 next actions, found ${nextActionCount}`);
  }
  const statusText = await desktop.locator('body').innerText();
  for (const forbidden of ['Signed-in return', 'Status poster', 'At a glance', 'Release and next step.', 'Current caution.']) {
    if (statusText.includes(forbidden)) {
      failures.push(`status: contains retired secondary surface "${forbidden}"`);
    }
  }
  results.push({ surface: 'status', decision_card_count: cardCount, next_action_count: nextActionCount });

  await desktop.close();

  writeJsonArtifact('MINIMAL_EXPERIENCE_GATE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    base_url: baseUrl,
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    failures,
    results,
  });

  writeMarkdownArtifact(
    'MINIMAL_EXPERIENCE_GATE.md',
    [
      '# Minimal Experience Gate',
      '',
      `- Generated: ${new Date().toISOString()}`,
      `- Base URL: ${baseUrl}`,
      '- Checks: homepage starts with one download action, avoids duplicate homepage download strips, downloads exposes lane buttons for every promoted release platform, one status decision card plus one next-action rail.',
      '',
      ...results.map((result) => `- ${String(result.surface)} checked`),
      ...(failures.length > 0 ? ['', '## Failures', '', ...failures.map((failure) => `- ${failure}`)] : []),
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
