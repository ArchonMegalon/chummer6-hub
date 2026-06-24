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

  expect(helpResponse.status()).toBe(200);
  expect(contactResponse.status()).toBe(200);
  expect(participateResponse.status()).toBe(200);

  const helpRobots = helpResponse.headers()['x-robots-tag'] || '';
  const contactRobots = contactResponse.headers()['x-robots-tag'] || '';
  const participateRobots = participateResponse.headers()['x-robots-tag'] || '';

  expect(helpRobots).toContain('index');
  expect(contactRobots).toContain('index');
  expect(participateRobots).toContain('noindex');

  const helpPage = await openPublicPage(browser, '/help');
  await expect(helpPage.getByRole('heading', { name: 'Get help without guessing' })).toBeVisible();
  await expect(helpPage.locator('body')).toContainText('Pick the problem');
  await expect(helpPage.getByRole('link', { name: 'Open downloads' })).toBeVisible();
  await expect(helpPage.getByRole('link', { name: 'Read the FAQ' })).toBeVisible();
  await helpPage.close();

  const contactPage = await openPublicPage(browser, '/contact');
  await expect(contactPage.getByRole('heading', { name: 'Open the right support case' })).toBeVisible();
  await expect(contactPage.locator('body')).toContainText('Use Participate for ideas and safe public bugs.');
  await expect(contactPage.getByRole('link', { name: 'Open participate' })).toBeVisible();
  await expect(contactPage.getByRole('link', { name: 'Open support intake' })).toBeVisible();
  await contactPage.close();

  const participatePage = await openPublicPage(browser, '/partizipate');
  await expect(participatePage.getByRole('heading', { name: 'Public requests, one board.' })).toBeVisible();
  await expect(participatePage.locator('body')).toContainText('Keep private support in Help.');

  const fallbackHeading = participatePage.getByRole('heading', { name: 'Fallback form' });
  const hostedHeading = participatePage.getByRole('heading', { name: 'Public board' });
  const usingFallback = await fallbackHeading.isVisible().catch(() => false);
  const usingHosted = await hostedHeading.isVisible().catch(() => false);

  expect(usingFallback || usingHosted).toBeTruthy();
  if (usingFallback) {
    await expect(participatePage.getByRole('button', { name: 'Send feedback' })).toBeVisible();
  } else {
    await expect(participatePage.locator('iframe.participate-hosted__frame')).toBeVisible();
  }
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
    participate_mode: usingFallback ? 'fallback_form' : 'hosted_board',
  });
});
