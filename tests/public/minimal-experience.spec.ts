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
  const heroPreview = desktop.locator('.minimal-hero__visual--preview');
  await expect(heroPreview).toBeVisible();
  await expect(heroPreview).toContainText('Desktop build. Mobile play packet.');
  await expect(heroPreview).toContainText('Track health, ammo, inventory, and modifiers.');
  await expect(desktop.locator('.minimal-hero__visual--screenshot')).toHaveCount(0);
  await expect(desktop.locator('.minimal-runner-rail')).toHaveCount(0);
  await expect(desktop.locator('[data-homepage-section="workflow"]')).toHaveCount(0);
  await expect(desktop.locator('[data-homepage-section="downloads"]')).toHaveCount(0);
  await expect(desktop.locator('.minimal-inline-links')).toContainText('Help');
  await expect(desktop.locator('.minimal-inline-links')).not.toContainText('Participate');
  await expect(desktop.locator('.minimal-inline-links')).not.toContainText('Status');
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
    hero_preview_visible: true,
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
  await expect(stableLane.getByRole('link')).toHaveCount(1);
  await expect(nightlyLane.getByRole('link')).toHaveCount(1);
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
  await expect(desktop).toHaveURL(/\/status(?:[?#].*)?$/);
  await expect(desktop.getByRole('heading', { name: /Preview downloads|Stable downloads|Downloads paused/ })).toBeVisible();
  await expect(desktop.locator('body')).toContainText('Now');
  await expect(desktop.locator('body')).toContainText(/downloads are live|download is live|Downloads are paused|No public installer right now/);
  await expect(desktop.getByRole('link', { name: 'Downloads' })).toBeVisible();
  await expect(desktop.getByRole('link', { name: 'Help' })).toBeVisible();
  const statusText = await desktop.locator('body').innerText();
  for (const forbidden of ['Signed-in return', 'Status poster', 'At a glance', 'Release and next step.', 'Current caution.', 'Platforms', 'Nightly', 'Build from source']) {
    if (statusText.includes(forbidden)) {
      failures.push(`status: contains retired secondary surface "${forbidden}"`);
    }
  }
  results.push({ surface: 'status', redirected_to_downloads: false });

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
      '- Checks: homepage starts with one download action, keeps a compact preview card instead of promo chrome, avoids duplicate homepage download strips, downloads exposes lane buttons for every promoted release platform, status uses compact next-action rail.',
      '',
      ...results.map((result) => `- ${String(result.surface)} checked`),
      ...(failures.length > 0 ? ['', '## Failures', '', ...failures.map((failure) => `- ${failure}`)] : []),
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
