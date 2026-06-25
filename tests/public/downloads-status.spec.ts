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
  await expect(downloadsPage.getByRole('heading', { name: 'Install Chummer' })).toBeVisible();
  await expect(downloadsPage.locator('body')).toContainText(/Current public installer/);
  await expect(downloadsPage.getByRole('heading', { name: 'Current build' })).toBeVisible();
  await expect(downloadsPage.getByRole('heading', { name: 'Newest build' })).toBeVisible();
  await expect(downloadsMain.getByRole('link', { name: 'Help' })).toBeVisible();
  await expect(downloadsMain.getByRole('link', { name: 'Status' })).toBeVisible();
  await downloadsPage.close();

  const statusPage = await openPublicPage(browser, '/status');
  await expect(statusPage.getByRole('heading', { name: 'Current release' })).toBeVisible();
  await expect(statusPage.locator('body')).toContainText('The build, platforms, and current state in one place.');
  await expect(statusPage.getByRole('link', { name: 'Open downloads' })).toBeVisible();
  await expect(statusPage.getByRole('link', { name: 'Open help' })).toBeVisible();
  await expect(statusPage.getByRole('heading', { name: 'Platforms' })).toBeVisible();
  await statusPage.close();

  writeJsonArtifact('DOWNLOADS_STATUS_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    downloads_status: downloadsResponse.status(),
    status_status: statusResponse.status(),
    downloads_robots: downloadsRobots,
    status_robots: statusRobots,
  });
});
