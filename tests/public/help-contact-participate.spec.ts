import { expect, test, type Browser } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

async function openPublicPage(browser: Browser, route: string) {
  const page = await browser.newPage({ baseURL: baseUrl });
  await page.goto(route, { waitUntil: 'domcontentloaded' });
  return page;
}

test('help, contact, and participate keep public and private paths clear', async ({ request, browser }) => {
  test.setTimeout(90000);

  const helpResponse = await request.get(`${baseUrl}/help`);
  const contactResponse = await request.get(`${baseUrl}/contact`);
  const participateResponse = await request.get(`${baseUrl}/partizipate`);
  const participateBoardResponse = await request.get(`${baseUrl}/partizipate/board`, { maxRedirects: 0 });

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
  expect(participateText).toContain('Public board');
  expect(participateText).toContain('Use the right place');
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
  await expect(contactPage.getByRole('link', { name: 'Open private help' })).toBeVisible();
  await contactPage.close();

  const participatePage = await openPublicPage(browser, '/partizipate');
  await expect(participatePage.getByRole('heading', { name: 'Participate' })).toBeVisible();
  await expect(participatePage.locator('body')).toContainText('Tell us what slows the table down.');
  await expect(participatePage.locator('body')).toContainText('Public board');
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
    participate_mode: 'public_wrapper',
  });
});
