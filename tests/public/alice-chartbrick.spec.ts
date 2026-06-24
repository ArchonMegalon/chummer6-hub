import { expect, request as playwrightRequest, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const identityToken = process.env.CHUMMER_E2E_IDENTITY_TOKEN?.trim() || '';
const localIdentityToken = process.env.CHUMMER_E2E_LOCAL_IDENTITY_TOKEN?.trim() || '';
const signedInToken = identityToken || localIdentityToken;

test('alice chartbrick panels render when configured', async ({ request, page }) => {
  test.setTimeout(90_000);

  const receiptResponse = await request.get(`${baseUrl}/alice/receipts/build-ghost.json`);
  expect(receiptResponse.status()).toBe(200);

  const payload = await receiptResponse.json();
  expect(Array.isArray(payload.insights)).toBeTruthy();
  expect(payload.insights.length).toBeGreaterThan(0);
  expect(payload.insights.some((item: { title?: string }) => item.title === 'Why ALICE leans this way')).toBeTruthy();
  expect(payload.insights.some((item: { title?: string }) => item.title === 'Runner stats')).toBeTruthy();

  await page.goto(`${baseUrl}/alice`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('h1')).toContainText('Character help');
  await expect(page.getByRole('heading', { name: 'See the shape before you commit to the path.' })).toBeVisible();
  await expect(page.locator('iframe[title="Why character help leans this way"]')).toHaveAttribute('src', /chartbrick\.com/i);
  await expect(page.locator('iframe[title="Runner stats"]')).toHaveAttribute('src', /chartbrick\.com/i);

  writeJsonArtifact('ALICE_CHARTBRICK_PUBLIC_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/alice',
    insight_count: payload.insights.length,
    insight_titles: payload.insights.map((item: { title?: string }) => item.title).filter(Boolean),
  });
});

test('signed-in alice handoff can show chartbrick runner boards', async ({ browser, request }) => {
  test.setTimeout(90_000);
  test.skip(!signedInToken, 'signed-in ALICE ChartBrick verification needs CHUMMER_E2E_IDENTITY_TOKEN or CHUMMER_E2E_LOCAL_IDENTITY_TOKEN');

  const parsedBaseUrl = new URL(baseUrl);
  const context = await browser.newContext();
  await context.addCookies([
    {
      name: 'chummer_hub_access_token',
      value: signedInToken,
      domain: parsedBaseUrl.hostname,
      path: '/',
      httpOnly: false,
      secure: parsedBaseUrl.protocol === 'https:',
      sameSite: 'Lax',
    },
  ]);

  const signedInRequest = await playwrightRequest.newContext({
    baseURL: baseUrl,
    extraHTTPHeaders: {
      Cookie: `chummer_hub_access_token=${signedInToken}`,
    },
  });

  const openResponse = await signedInRequest.get(`${baseUrl}/account/alice/open`, { maxRedirects: 0 });
  expect([302, 303]).toContain(openResponse.status());
  const location = openResponse.headers()['location'] || '';
  expect(location).toContain('/account/alice/');

  const page = await context.newPage();
  await page.goto(`${baseUrl}${location}`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText('ALICE boards');
  await expect(page.locator('body')).toContainText('See the current handoff before you commit.');
  await expect(page.locator('iframe[title="Why ALICE leans this way"]')).toHaveAttribute('src', /chartbrick\.com/i);
  await expect(page.locator('iframe[title="Runner stats"]')).toHaveAttribute('src', /chartbrick\.com/i);

  await signedInRequest.dispose();
  await page.close();
  await context.close();

  writeJsonArtifact('ALICE_CHARTBRICK_SIGNED_IN_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    open_route_status: openResponse.status(),
    handoff_location: location,
  });
});
