import { expect, request as playwrightRequest, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const identityToken = process.env.CHUMMER_E2E_IDENTITY_TOKEN?.trim() || '';

function containsSupportedBookLimitCopy(text: string) {
  return text.includes('1 book/month on Free. 2/month on Supporter.')
    || text.includes('Same app. 1 book each month on Free. 2 on Supporter.');
}

test('guest billing and account entry stay first-party', async ({ request }) => {
  const guestBilling = await request.get(`${baseUrl}/account/billing`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestBilling.status());
  const guestBillingLocation = guestBilling.headers()['location'] || '';
  expect(guestBillingLocation).toBe('/login?next=%2Faccount%2Fbilling');

  const guestAccount = await request.get(`${baseUrl}/account`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestAccount.status());
  const guestAccountLocation = guestAccount.headers()['location'] || '';
  expect(guestAccountLocation).toBe('/account/access');

  const guestSupporterStart = await request.get(`${baseUrl}/account/billing/supporter/start`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestSupporterStart.status());
  const guestSupporterStartLocation = guestSupporterStart.headers()['location'] || '';
  expect(guestSupporterStartLocation).toBe('/login?next=%2Faccount%2Fbilling');
});

test('billing and participate stay first-party for guests and signed-in users', async ({ request, browser }) => {
  test.setTimeout(90_000);

  const guestBilling = await request.get(`${baseUrl}/account/billing`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestBilling.status());
  const guestBillingLocation = guestBilling.headers()['location'] || '';
  expect(guestBillingLocation).toBe('/login?next=%2Faccount%2Fbilling');

  const guestParticipate = await request.get(`${baseUrl}/participate`);
  expect(guestParticipate.status()).toBe(200);
  const guestParticipateText = await guestParticipate.text();
  expect(guestParticipateText).toContain('What should Chummer do next?');
  expect(guestParticipateText).toContain('Public requests, clear bugs, useful ideas.');
  expect(guestParticipateText).toContain('Board is live.');
  expect(guestParticipateText).toContain('Current requests');
  expect(guestParticipateText).toContain('Sign in to Chummer');
  expect(guestParticipateText).toContain('data-chummer-participate-frame');
  expect(guestParticipateText).not.toContain('ProductLift');

  const guestSupporterStart = await request.get(`${baseUrl}/account/billing/supporter/start`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestSupporterStart.status());
  const guestSupporterStartLocation = guestSupporterStart.headers()['location'] || '';
  expect(guestSupporterStartLocation).toBe('/login?next=%2Faccount%2Fbilling');

  const guestAccount = await request.get(`${baseUrl}/account`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(guestAccount.status());
  const guestAccountLocation = guestAccount.headers()['location'] || '';
  expect(guestAccountLocation).toBe('/account/access');

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

  await page.goto(`${baseUrl}/account/billing?preview=true`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('h1')).toContainText('Membership');
  const billingBodyText = await page.locator('body').innerText();
  const signedInSupporterActive = billingBodyText.includes('Supporter is already attached to this account.');
  expect(containsSupportedBookLimitCopy(billingBodyText)).toBeTruthy();
  await expect(page.locator('body')).toContainText('No extra app features today.');
  if (signedInSupporterActive) {
    await expect(page.locator('body')).toContainText('Supporter is already attached to this account.');
  } else {
    await expect(page.locator('body')).toContainText('Checkout stays attached to this account.');
  }
  await expect(page.locator('body')).not.toContainText('external billing checkout');
  await expect(page.locator('body')).not.toContainText('hosted billing route');
  const supporterForm = page.locator('form[action="/account/billing/supporter"]');
  await expect(supporterForm).toBeVisible();
  const attachedUserId = await supporterForm.locator('input[name="userId"]').inputValue();
  const antiForgeryToken = await supporterForm.locator('input[name="__RequestVerificationToken"]').inputValue();
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
  const signedInBillingHandoff = await signedInRequest.get(`${baseUrl}/account/billing`, {
    maxRedirects: 0,
  });
  expect([302, 303]).toContain(signedInBillingHandoff.status());
  const signedInBillingLocation = signedInBillingHandoff.headers()['location'] || '';
  if (signedInSupporterActive) {
    expect(signedInBillingLocation).toContain('billing.example.test/portal');
  } else {
    expect(signedInBillingLocation).toContain('billing.example.test/supporter');
    expect(signedInBillingLocation).toContain('external_user=');
    expect(signedInBillingLocation).toContain('membership_plan=supporter');
  }
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

  await page.goto(`${baseUrl}/participate`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'What should Chummer do next?' })).toBeVisible();
  await expect(page.locator('body')).toContainText('Public requests, clear bugs, useful ideas.');
  await expect(page.locator('body')).toContainText('Current requests');
  await expect(page.locator('body')).not.toContainText('Board offline right now');
  await expect(page.locator('[data-chummer-participate-frame]')).toHaveCount(1);
  await expect(page.locator('body')).toContainText('Board is live.');
  await expect(page.getByRole('link', { name: 'Account' })).toHaveAttribute('href', '/account');
  await expect(page.getByRole('link', { name: 'Supporter' })).toHaveAttribute('href', '/account/billing');
  await expect(page.locator('body')).not.toContainText('ProductLift');
  await expect(page.locator('body')).not.toContainText('Log in');
  await expect(page.locator('body')).not.toContainText('Sign up');
  await page.close();
  await context.close();

  writeJsonArtifact('PARTICIPATE_BILLING_AUTH_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    guest_billing_status: guestBilling.status(),
    guest_billing_location: guestBillingLocation,
    guest_participate_status: guestParticipate.status(),
    guest_participate_public_wrapper: true,
    guest_participate_surface: 'first_party_iframe_shell',
    guest_supporter_start_status: guestSupporterStart.status(),
    guest_supporter_start_location: guestSupporterStartLocation,
    guest_account_status: guestAccount.status(),
    guest_account_location: guestAccountLocation,
    signed_in_supporter_checkout_status: signedInSupporterCheckout.status(),
    signed_in_supporter_checkout_location: signedInSupporterLocation,
    signed_in_supporter_direct_status: signedInSupporterDirect.status(),
    signed_in_supporter_direct_location: signedInSupporterDirectLocation,
    signed_in_billing_handoff_status: signedInBillingHandoff.status(),
    signed_in_billing_handoff_location: signedInBillingLocation,
    signed_in_supporter_active: signedInSupporterActive,
    signed_in_participate_first_party_verified: true,
    signed_in_participate_surface: 'first_party_iframe_shell',
    signed_in_identity_token_present: true,
    first_party_sign_in_redirect: guestSupporterStartLocation === '/login?next=%2Faccount%2Fbilling',
  });
});
