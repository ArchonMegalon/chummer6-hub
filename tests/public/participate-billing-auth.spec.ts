import { expect, request as playwrightRequest, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const identityToken = process.env.CHUMMER_E2E_IDENTITY_TOKEN?.trim() || '';
const boardSentinel = process.env.CHUMMER_E2E_BOARD_SENTINEL?.trim() || 'board sentinel';
const boardBaseUrl = process.env.CHUMMER_E2E_BOARD_BASE_URL?.trim() || '';

test('billing and participate stay first-party for guests and signed-in users', async ({ request, browser }) => {
  test.setTimeout(90_000);

  const guestBilling = await request.get(`${baseUrl}/account/billing`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestBilling.status());
  const guestLocation = guestBilling.headers()['location'] || '';
  expect(guestLocation).toContain('/auth/google/start?next=');
  expect(guestLocation).toContain('%2Faccount%2Fbilling');

  const guestParticipate = await request.get(`${baseUrl}/participate`);
  expect(guestParticipate.status()).toBe(200);
  const guestParticipateText = await guestParticipate.text();
  expect(guestParticipateText).toContain('participate-board');
  expect(guestParticipateText).toContain('/participate/board');
  expect(guestParticipateText).not.toContain('Requests, votes, and shipped work.');
  expect(guestParticipateText).not.toContain('Support Chummer');
  expect(guestParticipateText).not.toContain('ProductLift');

  const guestSupporterStart = await request.get(`${baseUrl}/account/billing/supporter/start`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestSupporterStart.status());
  const guestSupporterStartLocation = guestSupporterStart.headers()['location'] || '';
  expect(guestSupporterStartLocation).toContain('/auth/google/start?next=');
  expect(guestSupporterStartLocation).toContain('%2Faccount%2Fbilling%2Fsupporter%2Fstart');

  test.skip(!identityToken, 'signed-in billing verification needs CHUMMER_E2E_IDENTITY_TOKEN');

  const parsedBaseUrl = new URL(baseUrl);
  const context = await browser.newContext();
  await context.addCookies([
    {
      name: 'chummer_hub_access_token',
      value: identityToken,
      domain: parsedBaseUrl.hostname,
      path: '/',
      httpOnly: false,
      secure: parsedBaseUrl.protocol === 'https:',
      sameSite: 'Lax',
    },
  ]);
  const page = await context.newPage();

  await page.goto(`${baseUrl}/account/billing`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('h1')).toContainText('Membership');
  await expect(page.locator('body')).toContainText('Same app for everyone.');
  await expect(page.locator('body')).toContainText('Origin books: Free 1/month. Supporter 2/month.');
  await expect(page.locator('body')).toContainText('Signed in as');
  await expect(page.locator('body')).toContainText('Supporter does not unlock extra app features right now.');
  await expect(page.locator('body')).not.toContainText('external billing checkout');
  await expect(page.locator('body')).not.toContainText('hosted billing route');
  await expect(page.locator('form[action="/account/billing/supporter"]')).toBeVisible();
  const attachedUserId = await page.locator('input[name="userId"]').inputValue();
  const antiForgeryToken = await page.locator('input[name="__RequestVerificationToken"]').inputValue();
  expect(attachedUserId.length).toBeGreaterThan(0);
  expect(antiForgeryToken.length).toBeGreaterThan(0);

  const cookieHeader = (await context.cookies())
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join('; ');
  const signedInRequest = await playwrightRequest.newContext({
    baseURL: baseUrl,
    extraHTTPHeaders: {
      Cookie: cookieHeader,
    },
  });
  const signedInSupporterCheckout = await signedInRequest.post(`${baseUrl}/account/billing/supporter`, {
    maxRedirects: 0,
    form: {
      __RequestVerificationToken: antiForgeryToken,
      userId: attachedUserId,
      email: 'runner@example.com',
    },
  });
  expect([302, 303]).toContain(signedInSupporterCheckout.status());
  const signedInSupporterLocation = signedInSupporterCheckout.headers()['location'] || '';
  expect(signedInSupporterLocation).toContain('billing.example.test/supporter');
  expect(signedInSupporterLocation).toContain('external_user=');
  expect(signedInSupporterLocation).toContain('membership_plan=supporter');

  const signedInSupporterDirect = await signedInRequest.get(`${baseUrl}/account/billing/supporter/start`, {
    maxRedirects: 0,
  });
  expect([302, 303]).toContain(signedInSupporterDirect.status());
  const signedInSupporterDirectLocation = signedInSupporterDirect.headers()['location'] || '';
  expect(signedInSupporterDirectLocation).toContain('billing.example.test/supporter');
  expect(signedInSupporterDirectLocation).toContain('external_user=');
  expect(signedInSupporterDirectLocation).toContain('membership_plan=supporter');
  await signedInRequest.dispose();

  if (boardBaseUrl) {
    await page.goto(`${baseUrl}/participate`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('body')).toContainText(boardSentinel);
    await expect(page.getByRole('link', { name: 'Support Chummer' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Support Chummer' })).toHaveAttribute('href', '/account/billing/supporter/start');
    await expect(page.locator('body')).not.toContainText('Log in');
    await expect(page.locator('body')).not.toContainText('Sign up');
    await expect(page.locator('body')).not.toContainText('Sign in');

    const signedInParticipate = await request.get(`${baseUrl}/participate`, {
      maxRedirects: 0,
      headers: {
        Cookie: `chummer_hub_access_token=${identityToken}`,
      },
    });
    expect(signedInParticipate.status()).toBe(200);
    const signedInParticipateText = await signedInParticipate.text();
    expect(signedInParticipateText).toContain(boardSentinel);
    expect(signedInParticipateText).not.toContain(boardBaseUrl);
    expect(signedInParticipateText).toContain('/participate/board/');
    expect(signedInParticipateText).toContain('/account/billing/supporter/start');
    expect(signedInParticipateText).toContain('Support Chummer');
    expect(signedInParticipateText).not.toContain('Sign in');
  }
  await page.close();
  await context.close();

  writeJsonArtifact('PARTICIPATE_BILLING_AUTH_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    guest_billing_status: guestBilling.status(),
    guest_billing_location: guestLocation,
    guest_participate_status: guestParticipate.status(),
    guest_participate_public_wrapper: true,
    guest_supporter_start_status: guestSupporterStart.status(),
    guest_supporter_start_location: guestSupporterStartLocation,
    signed_in_supporter_checkout_status: signedInSupporterCheckout.status(),
    signed_in_supporter_checkout_location: signedInSupporterLocation,
    signed_in_supporter_direct_status: signedInSupporterDirect.status(),
    signed_in_supporter_direct_location: signedInSupporterDirectLocation,
    signed_in_participate_proxy_verified: Boolean(boardBaseUrl),
    signed_in_identity_token_present: true,
    first_party_sign_in_redirect: guestLocation.includes('/auth/google/start?next='),
  });
});
