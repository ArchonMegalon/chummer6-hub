import { expect, test, type Browser } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

async function openPublicPage(browser: Browser, route: string) {
  const page = await browser.newPage({ baseURL: baseUrl });
  await page.goto(route, { waitUntil: 'domcontentloaded' });
  return page;
}

test('downloads and status stay concise and point to the right next steps', async ({ request, browser }) => {
  test.setTimeout(90000);

  const downloadsResponse = await request.get(`${baseUrl}/downloads`);
  const statusResponse = await request.get(`${baseUrl}/status`);

  expect(downloadsResponse.status()).toBe(200);
  expect(statusResponse.status()).toBe(200);

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
  await expect(downloadsPage.locator('body')).toContainText(/Stable release/);
  await expect(downloadsPage.locator('body')).toContainText('Nightly handoff');
  await expect(downloadsPage.locator('body')).toContainText('Build from source');
  await expect(downloadsMain.getByRole('link', { name: /Download for|Download script|Use Nightly|Use Stable/ })).toHaveCount(2);
  await downloadsPage.close();

  const statusPage = await openPublicPage(browser, '/status');
  await expect(statusPage).toHaveURL(/\/status(?:[?#].*)?$/);
  await expect(statusPage.getByRole('heading', { name: 'Updated' })).toBeVisible();
  await expect(statusPage.locator('.minimal-page-hero.minimal-status-pill')).toBeVisible();
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
  });
});
