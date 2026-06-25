import { expect, test, type Browser } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

async function openPublicPage(browser: Browser, route: string) {
  let lastNetworkError: unknown;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const page = await browser.newPage({ baseURL: baseUrl });
    try {
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      return page;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await page.close().catch(() => undefined);
      if (!message.includes('ERR_NETWORK_CHANGED')) {
        throw error;
      }
      lastNetworkError = error;
      await new Promise(resolve => setTimeout(resolve, 750 * (attempt + 1)));
    }
  }
  throw lastNetworkError instanceof Error
    ? lastNetworkError
    : new Error(String(lastNetworkError));
}

test('help, contact, and participate keep public and private paths clear', async ({ request, browser }) => {
  test.setTimeout(90000);

  const helpResponse = await request.get(`${baseUrl}/help`);
  const contactResponse = await request.get(`${baseUrl}/contact`);
  const participateResponse = await request.get(`${baseUrl}/participate`);
  const participateBoardResponse = await request.get(`${baseUrl}/participate/board`, { maxRedirects: 0 });

  expect(helpResponse.status()).toBe(200);
  expect(contactResponse.status()).toBe(200);
  expect(participateResponse.status()).toBe(200);
  expect(participateBoardResponse.status()).toBe(200);

  const helpRobots = helpResponse.headers()['x-robots-tag'] || '';
  const contactRobots = contactResponse.headers()['x-robots-tag'] || '';
  const participateRobots = participateResponse.headers()['x-robots-tag'] || '';
  const participateText = await participateResponse.text();
  const participateBoardText = await participateBoardResponse.text();

  expect(helpRobots).toContain('index');
  expect(contactRobots).toContain('index');
  expect(participateText).toContain('partizipate-board');
  expect(participateText).toContain('Short requests, clear bugs, useful ideas.');
  expect(participateText).not.toContain('participate-board');
  expect(participateText).not.toContain('/participate/board');
  expect(participateText).not.toContain('Requests, votes, and shipped work.');
  expect(participateText).not.toContain('ProductLift');
  expect(participateBoardText).not.toContain('/auth/google/start?next=');

  const helpPage = await openPublicPage(browser, '/help');
  await expect(helpPage.getByRole('heading', { name: 'Get help without guessing' })).toBeVisible();
  await expect(helpPage.locator('body')).toContainText('Pick the problem');
  await expect(helpPage.getByRole('link', { name: 'Open downloads' })).toBeVisible();
  await expect(helpPage.getByRole('link', { name: 'Read the FAQ' })).toBeVisible();
  await helpPage.close();

  const contactPage = await openPublicPage(browser, '/contact');
  await expect(contactPage.getByRole('heading', { name: 'Contact Chummer' })).toBeVisible();
  await expect(contactPage.locator('body')).toContainText('Public ideas go to Participate. Private problems stay here.');
  await expect(contactPage.getByRole('link', { name: 'Open participate' })).toBeVisible();
  await expect(contactPage.getByRole('link', { name: 'Open support' })).toBeVisible();
  await contactPage.close();

  const participatePage = await openPublicPage(browser, '/participate');
  await expect(participatePage.getByRole('heading', { name: 'Participate' })).toHaveCount(1);
  await expect(participatePage.locator('.partizipate-board')).toBeVisible();
  await expect(participatePage.locator('#participate-board')).toHaveCount(0);
  await expect(participatePage.locator('body')).not.toContainText('Requests, votes, and shipped work.');
  await expect(participatePage.locator('body')).not.toContainText('ProductLift');
  await participatePage.close();

  writeJsonArtifact('HELP_CONTACT_PARTICIPATE_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    help_status: helpResponse.status(),
    contact_status: contactResponse.status(),
    participate_status: participateResponse.status(),
    help_robots: helpRobots,
    contact_robots: contactRobots,
    participate_robots: participateRobots,
    participate_mode: 'first_party_board',
  });
});
