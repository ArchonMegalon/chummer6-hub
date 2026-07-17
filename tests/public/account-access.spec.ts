import { expect, test } from 'playwright/test';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const hostedIdentityToken = process.env.CHUMMER_E2E_IDENTITY_TOKEN?.trim() || '';
const localIdentityToken = process.env.CHUMMER_E2E_LOCAL_IDENTITY_TOKEN?.trim() || '';
const identityToken = hostedIdentityToken || localIdentityToken;
const requireSignedInAccountProof = process.env.CHUMMER_REQUIRE_SIGNED_IN_ACCOUNT_PROOF?.trim() === '1';
const safeHttpMethods = new Set(['GET', 'HEAD', 'OPTIONS']);

function isLoopbackHost(hostname: string) {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]';
}

function parseExplicitlyAllowedHostedOrigins() {
  const values = process.env.CHUMMER_E2E_ACCOUNT_PROOF_ALLOWED_ORIGINS
    ?.split(',')
    .map((value) => value.trim())
    .filter(Boolean) || [];
  return new Set(values.map((value) => {
    const candidate = new URL(value);
    if (candidate.protocol !== 'https:'
      || candidate.username
      || candidate.password
      || (candidate.pathname !== '/' && candidate.pathname !== '')
      || candidate.search
      || candidate.hash) {
      throw new Error(`Unsafe account proof allowlisted origin: ${value}`);
    }
    return candidate.origin;
  }));
}

function safeIdentityTokenTarget(value: string) {
  const target = new URL(value);
  if (target.username
    || target.password
    || (target.pathname !== '/' && target.pathname !== '')
    || target.search
    || target.hash) {
    throw new Error('Account proof BASE_URL must be an origin without credentials, path, query, or fragment.');
  }
  if (hostedIdentityToken && localIdentityToken) {
    throw new Error('Set only one hosted or local account proof identity token.');
  }
  if (localIdentityToken) {
    if (!isLoopbackHost(target.hostname) || !['http:', 'https:'].includes(target.protocol)) {
      throw new Error('Local account proof tokens may only target an HTTP(S) loopback origin.');
    }
    return target;
  }

  const allowedHostedOrigins = parseExplicitlyAllowedHostedOrigins();
  allowedHostedOrigins.add('https://chummer.run');
  if (target.protocol !== 'https:' || !allowedHostedOrigins.has(target.origin)) {
    throw new Error(`Refusing to place a hosted account proof token on unapproved origin ${target.origin}.`);
  }
  return target;
}

function expectPrivateNoStore(headers: Record<string, string>) {
  expect(headers['cache-control'] || '').toContain('private');
  expect(headers['cache-control'] || '').toContain('no-store');
  expect(headers['cdn-cache-control']).toBe('no-store, max-age=0');
  expect(headers['cloudflare-cdn-cache-control']).toBe('no-store, max-age=0');
  expect(headers['surrogate-control']).toBe('no-store');
  expect(headers.pragma).toContain('no-cache');
  expect(headers.expires).toBe('0');
}

test('account entry redirects remain private and non-cacheable', async ({ request }) => {
  for (const route of ['/account', '/account/access']) {
    const response = await request.get(`${baseUrl}${route}`, { maxRedirects: 0 });
    expect([302, 303, 307, 308]).toContain(response.status());
    expectPrivateNoStore(response.headers());
  }
});

test('signed-in account access stays quiet, responsive, and semantically focused', async ({ browser }) => {
  if (!identityToken) {
    if (requireSignedInAccountProof) {
      throw new Error('Release account proof requires CHUMMER_E2E_IDENTITY_TOKEN or CHUMMER_E2E_LOCAL_IDENTITY_TOKEN.');
    }
    test.skip(true, 'optional developer proof needs CHUMMER_E2E_IDENTITY_TOKEN or CHUMMER_E2E_LOCAL_IDENTITY_TOKEN');
  }

  // Validate the entire target boundary before creating a context or installing a credential.
  const parsedBaseUrl = safeIdentityTokenTarget(baseUrl);
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 1280, height: 900 },
  ]) {
    const unsafeMethodAttempts: string[] = [];
    const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
    try {
      await context.route('**/*', async (route) => {
        const request = route.request();
        const method = request.method().toUpperCase();
        if (!safeHttpMethods.has(method)) {
          unsafeMethodAttempts.push(method);
          await route.abort('blockedbyclient');
          return;
        }
        await route.continue();
      });
      await context.addCookies([
        {
          name: 'chummer_hub_access_token',
          value: identityToken,
          url: `${parsedBaseUrl.origin}/`,
          httpOnly: true,
          secure: parsedBaseUrl.protocol === 'https:',
          sameSite: 'Lax',
        },
      ]);
      const page = await context.newPage();
      const response = await page.goto(`${parsedBaseUrl.origin}/account/access`, { waitUntil: 'domcontentloaded' });
      expect(response).not.toBeNull();
      expect(response?.status()).toBe(200);
      expectPrivateNoStore(response?.headers() || {});

      const hero = page.locator('section[data-account-access]');
      await expect(hero).toHaveCount(1);
      await expect(hero).toHaveAttribute('aria-labelledby', 'account-access-title');
      await expect(page.getByRole('heading', { level: 1, name: 'Install Chummer' })).toHaveCount(1);
      await expect(hero.locator('[data-account-access-primary]')).toHaveCount(1);
      await expect(hero.locator('[data-account-access-primary]')).toHaveAccessibleName('Download Chummer');
      await expect(page.getByRole('region', { name: 'Install help' })).toHaveCount(1);

      const bodyText = await page.locator('body').innerText();
      for (const noisyCopy of [
        'Recent install handoffs',
        'Cross-device recovery',
        'Advanced device recovery',
        'Offline-ready return',
        'What stays on this device',
        'How install linking works',
      ]) {
        expect(bodyText).not.toContain(noisyCopy);
      }
      expect(bodyText).not.toContain(identityToken);
      expect(await page.evaluate(() => document.cookie)).not.toContain('chummer_hub_access_token');

      const layout = await page.evaluate(() => {
        const heroElement = document.querySelector<HTMLElement>('section[data-account-access]');
        const copiesElement = document.querySelector<HTMLElement>('section[data-account-access-copies]');
        const helpElement = document.querySelector<HTMLElement>('.account-access__help');
        return {
          overflowX: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth,
          widths: [heroElement, copiesElement, helpElement]
            .filter((element): element is HTMLElement => Boolean(element))
            .map((element) => element.getBoundingClientRect().width),
        };
      });
      expect(layout.overflowX).toBeLessThanOrEqual(1);
      for (const width of layout.widths) {
        expect(width).toBeLessThanOrEqual(Math.min(viewport.width, 704) + 1);
      }

      const unlinkButtons = page.locator('form[action="/account/access/unlink"] button[type="submit"]');
      for (let index = 0; index < await unlinkButtons.count(); index += 1) {
        await expect(unlinkButtons.nth(index)).toHaveAccessibleName(/^Unlink .+/);
      }

      await page.waitForLoadState('load');
      expect(unsafeMethodAttempts, 'signed-in account proof must not attempt mutating HTTP methods').toEqual([]);
    } finally {
      await context.close();
    }
  }
});
