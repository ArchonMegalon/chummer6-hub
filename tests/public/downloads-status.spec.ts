import { expect, test, type Browser } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const stableChannels = new Set(['public_stable', 'stable']);
const recognizedStatusHeadings = new Set([
  'Downloads under review',
  'Preview downloads',
  'Stable downloads',
  'Downloads paused',
]);
const blockingRolloutStates = new Set([
  'blocked',
  'coverage_incomplete',
  'desktop_polish_needed',
  'disabled',
  'public_release_review_required',
  'release_review_required',
  'revoked',
  'unpublished',
]);

function normalizedText(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

function publicInstallerAvailable(manifest: Record<string, unknown>): boolean {
  if (Array.isArray(manifest.downloads)) {
    return manifest.downloads.length > 0;
  }
  if (Array.isArray(manifest.artifacts)) {
    return manifest.artifacts.some((value) => {
      if (!value || typeof value !== 'object') return false;
      const artifact = value as Record<string, unknown>;
      const kind = normalizedText(artifact.kind ?? artifact.artifactKind);
      const access = normalizedText(
        artifact.installAccessClass ?? artifact.accessClass ?? artifact.access,
      );
      const url = normalizedText(artifact.downloadUrl ?? artifact.url ?? artifact.installUrl);
      return kind.includes('installer')
        && (!access || ['open_public', 'public', 'guest'].includes(access))
        && !!url;
    });
  }
  const publicInstallCount = (
    manifest.publicTrustMetrics as Record<string, unknown> | undefined
  )?.adoptionHealth as Record<string, unknown> | undefined;
  if (publicInstallCount && 'publicInstallCount' in publicInstallCount) {
    return Number(publicInstallCount.publicInstallCount || 0) > 0;
  }
  return true;
}

function expectedStatusHeadingFromManifest(manifest: Record<string, unknown>): string {
  const status = normalizedText(manifest.status);
  const version = typeof manifest.version === 'string' ? manifest.version.trim() : '';
  const channel = normalizedText(manifest.channel ?? manifest.channelId ?? manifest.channel_id);
  const supportabilityState = normalizedText(manifest.supportabilityState ?? manifest.supportability_state);
  const rolloutState = normalizedText(manifest.rolloutState ?? manifest.rollout_state);
  const statusAllowsStableRelease = !status || status === 'published';
  const isPublishedStableRelease = (
    statusAllowsStableRelease
    && supportabilityState === 'gold_supported'
    && (stableChannels.has(channel) || rolloutState === 'public_stable')
  );

  if (
    statusAllowsStableRelease
    && supportabilityState === 'review_required'
    && publicInstallerAvailable(manifest)
    && (version || channel || blockingRolloutStates.has(rolloutState))
  ) {
    return 'Downloads under review';
  }

  if (status && status !== 'published') {
    return 'Downloads paused';
  }

  if (isPublishedStableRelease) {
    return 'Stable downloads';
  }

  if (
    channel === 'preview'
    || rolloutState === 'promoted_preview'
    || supportabilityState === 'preview_supported'
    || stableChannels.has(channel)
    || rolloutState === 'public_stable'
    || supportabilityState === 'gold_supported'
    || version
  ) {
    return 'Preview downloads';
  }

  return 'Downloads paused';
}

async function openPublicPage(browser: Browser, route: string) {
  const page = await browser.newPage({ baseURL: baseUrl });
  await page.goto(route, { waitUntil: 'domcontentloaded' });
  return page;
}

test('downloads and status stay concise and point to the right next steps', async ({ request, browser }) => {
  test.setTimeout(90000);

  const downloadsResponse = await request.get(`${baseUrl}/downloads`);
  const statusResponse = await request.get(`${baseUrl}/status`);
  const releaseManifestResponse = await request.get(`${baseUrl}/downloads/RELEASE_CHANNEL.generated.json`);

  expect(downloadsResponse.status()).toBe(200);
  expect(statusResponse.status()).toBe(200);
  expect(releaseManifestResponse.status()).toBe(200);

  const releaseManifest = await releaseManifestResponse.json();
  const expectedStatusHeading = expectedStatusHeadingFromManifest(releaseManifest);

  const downloadsRobots = downloadsResponse.headers()['x-robots-tag'] || '';
  const statusRobots = statusResponse.headers()['x-robots-tag'] || '';
  expect(downloadsRobots).toContain('index');
  expect(statusRobots).toContain('index');

  const downloadsPage = await openPublicPage(browser, '/downloads');
  const downloadsMain = downloadsPage.locator('#main');
  await expect(downloadsPage.getByRole('heading', { name: 'Downloads' })).toBeVisible();
  await expect(downloadsPage.locator('body')).toContainText('Stable');
  await expect(downloadsPage.locator('body')).toContainText('Nightly');
  await expect(downloadsPage.locator('body')).toContainText('Chummer selects the best installer when it can.');
  const downloadsVersionMarker = downloadsMain.locator('[data-downloads-release-version]');
  await expect(downloadsVersionMarker).toContainText(/^Version \S+/);
  const downloadsVersionText = (await downloadsVersionMarker.textContent())?.trim() || '';
  await expect(downloadsPage.locator('body')).toContainText(
    /Stable release|No Stable build on this shelf\.|Stable release is unchanged while this nightly handoff is under review\.|Stable release is not available for this platform yet\./,
  );
  await expect(downloadsPage.locator('body')).toContainText(
    /Nightly handoff|No newer Nightly right now\.|Preview build\. Check Help before you install\./,
  );
  await expect(downloadsPage.locator('body')).toContainText('Build from source');
  const primaryLaneActions = await downloadsMain.locator('#stable a.button-like, #nightly a.button-like').evaluateAll(
    (items) => items.map((item) => ({
      text: (item.textContent ?? '').trim(),
      href: item.getAttribute('href') ?? '',
    })).filter((item) => item.text),
  );
  expect(primaryLaneActions).toHaveLength(2);
  for (const action of primaryLaneActions) {
    expect(
      action.text === 'Use Nightly'
      || action.text === 'Use Stable'
      || action.text === 'Other downloads'
      || action.text.startsWith('Download for'),
    ).toBe(true);
    expect(
      action.href === '#nightly'
      || action.href === '#stable'
      || action.href === '#other-downloads'
      || action.href.startsWith('/downloads/'),
    ).toBe(true);
  }
  await downloadsPage.close();

  const statusPage = await openPublicPage(browser, '/status');
  await expect(statusPage).toHaveURL(/\/status(?:[?#].*)?$/);
  const statusHero = statusPage.locator('.minimal-page-hero.minimal-status-pill');
  await expect(statusHero).toBeVisible();
  await expect(statusHero).toContainText(/Now|Updated/);
  await expect(statusHero).toContainText(/Downloads under review|Preview downloads|Stable downloads|Downloads paused/);
  const statusHeadingText = (await statusHero.locator('h1').textContent())?.trim() || '';
  const statusHeadingRecognized = recognizedStatusHeadings.has(statusHeadingText);
  const statusHeadingMatchesReleaseChannel = statusHeadingText === expectedStatusHeading;
  const statusHeadingUsesGenericUpdatedCopy = statusHeadingText === 'Updated';
  expect(statusHeadingRecognized).toBe(true);
  expect(statusHeadingMatchesReleaseChannel).toBe(true);
  expect(statusHeadingUsesGenericUpdatedCopy).toBe(false);
  const statusVersionMarker = statusPage.locator('[data-downloads-release-version]');
  await expect(statusVersionMarker).toContainText(/^Version \S+/);
  const statusVersionText = (await statusVersionMarker.textContent())?.trim() || '';
  const statusActions = statusPage.getByLabel('Status next actions');
  await expect(statusActions.getByRole('link', { name: 'Downloads' })).toBeVisible();
  await expect(statusActions.getByRole('link', { name: 'Help' })).toBeVisible();
  await expect(statusPage.getByRole('heading', { name: 'Platforms' })).toHaveCount(0);
  await statusPage.close();

  writeJsonArtifact('DOWNLOADS_STATUS_E2E.generated.json', {
    contractName: 'chummer.downloads_status_e2e.v1',
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    downloads_status: downloadsResponse.status(),
    status_status: statusResponse.status(),
    downloads_robots: downloadsRobots,
    status_robots: statusRobots,
    downloads_version_marker: true,
    status_redirect_version_marker: true,
    downloads_version_text: downloadsVersionText,
    status_redirect_version_text: statusVersionText,
    status_redirect_heading: statusHeadingText,
    status_redirect_heading_recognized: statusHeadingRecognized,
    status_redirect_heading_expected: expectedStatusHeading,
    status_redirect_heading_matches_release_channel: statusHeadingMatchesReleaseChannel,
    status_redirect_heading_uses_generic_updated_copy: statusHeadingUsesGenericUpdatedCopy,
  });
});
