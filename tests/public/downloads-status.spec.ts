import { expect, test, type Browser } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const stableChannels = new Set(['public_stable', 'stable']);
const recognizedStatusHeadings = new Set(['Preview downloads', 'Stable downloads', 'Downloads paused']);

function normalizedText(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : '';
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
  await expect(downloadsVersionMarker).toHaveAttribute('data-downloads-release-version', /^Version \S+/);
  const downloadsVersionText = normalizedText((await downloadsMain.locator('.downloads-version').first().textContent()) || '');
  const hasStableReleaseCopy = (await downloadsPage.locator('text=Stable release.').count()) > 0;
  const hasNoStableCopy = (await downloadsPage.locator('text=No Stable build on this shelf.').count()) > 0;
  const hasPreviewRequiredCopy = (await downloadsPage.locator('text=Preview build. Review required.').count()) > 0;
  expect(hasStableReleaseCopy || hasNoStableCopy).toBeTruthy();
  if (hasStableReleaseCopy) {
    await expect(downloadsPage.locator('body')).toContainText('Stable release.');
    await expect(downloadsPage.locator('body')).not.toContainText('Preview build. Review required.');
    await expect(downloadsPage.locator('body')).not.toContainText('No Stable build on this shelf.');
  } else {
    expect(hasNoStableCopy).toBeTruthy();
    await expect(downloadsPage.locator('body')).toContainText('No Stable build on this shelf.');
    await expect(downloadsPage.locator('body')).toContainText('Preview build. Review required.');
  }
  await expect(downloadsPage.locator('body')).toContainText('Build from source');
  const stableDownload = downloadsMain.locator('#stable');
  const stableDownloadLink = stableDownload.locator('[data-release-lane="stable"]');
  await expect(stableDownload).toBeVisible();
  if (hasStableReleaseCopy) {
    await expect(stableDownloadLink).toHaveAttribute('data-download-artifact', /avalonia-.+/);
    await expect(stableDownloadLink).toHaveAttribute('data-release-lane', 'stable');
    await expect(stableDownload.getByRole('link')).toHaveCount(1);
    await expect(stableDownload.getByRole('link', { name: /Download for|Use Stable/ })).toBeVisible();
  } else {
    await expect(stableDownload.getByRole('link', { name: 'Other downloads' })).toBeVisible();
    await expect(stableDownload.getByRole('link', { name: /Download for|Use Stable|Downloads are paused/ })).toHaveCount(0);
  }
  expect(await downloadsMain.getByRole('link').count()).toBeGreaterThanOrEqual(2);
  await downloadsPage.close();

  const statusPage = await openPublicPage(browser, '/status');
  await expect(statusPage).toHaveURL(/\/status(?:[?#].*)?$/);
  const statusHeading = statusPage.getByRole('heading', { level: 1 });
  await expect(statusHeading).toBeVisible();
  const statusHeadingText = (await statusHeading.textContent())?.trim() || '';
  const statusHeadingRecognized = recognizedStatusHeadings.has(statusHeadingText);
  const statusHeadingUsesGenericUpdatedCopy = statusHeadingText === 'Updated';
  const statusHeadingMatchesReleaseChannel = statusHeadingText === expectedStatusHeading;
  expect(statusHeadingRecognized).toBeTruthy();
  expect(statusHeadingUsesGenericUpdatedCopy).toBeFalsy();
  expect(statusHeadingText).toBe(expectedStatusHeading);
  await expect(statusPage.locator('body')).toContainText('Now');
  await expect(statusPage.locator('body')).toContainText(/downloads are live|download is live|Downloads are paused|No public installer right now/);
  const statusVersionMarker = statusPage.locator('[data-downloads-release-version]');
  await expect(statusVersionMarker).toHaveAttribute('data-downloads-release-version', /^Version \S+/);
  const statusVersionText = (await statusVersionMarker.getAttribute('data-downloads-release-version'))?.trim() || '';
  const statusActions = statusPage.getByLabel('Status next actions');
  await expect(statusActions.getByRole('link', { name: 'Downloads' })).toBeVisible();
  await expect(statusActions.getByRole('link', { name: 'Help' })).toBeVisible();
  await expect(statusPage.locator('body')).not.toContainText('No Stable build on this shelf.');
  await expect(statusPage.locator('body')).not.toContainText('Preview build. Review required.');
  await expect(statusPage.locator('body')).not.toContainText('Nightly');
  await expect(statusPage.locator('body')).not.toContainText('Build from source');
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
    release_manifest_status: normalizedText(releaseManifest.status),
    release_manifest_channel: normalizedText(releaseManifest.channel ?? releaseManifest.channelId ?? releaseManifest.channel_id),
    release_manifest_supportability_state: normalizedText(releaseManifest.supportabilityState ?? releaseManifest.supportability_state),
    release_manifest_rollout_state: normalizedText(releaseManifest.rolloutState ?? releaseManifest.rollout_state),
  });
});
