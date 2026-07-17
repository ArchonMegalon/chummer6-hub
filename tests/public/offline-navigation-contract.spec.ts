import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createContext, runInContext } from 'node:vm';
import { expect, test } from 'playwright/test';

const serviceWorkerPath = path.join(process.cwd(), 'Chummer.Run.Api/wwwroot/service-worker.js');

type FetchEventFixture = {
  request: {
    method: string;
    mode: string;
    destination: string;
    url: string;
  };
  respondWith: (response: Promise<Response> | Response) => void;
  waitUntil: (work: Promise<unknown>) => void;
};

function createOfflineWorkerHarness() {
  const listeners = new Map<string, (event: FetchEventFixture) => void>();
  let cacheReads = 0;
  const context = createContext({
    URL,
    Request,
    Response,
    fetch: async () => {
      throw new TypeError('network unavailable');
    },
    caches: {
      match: async () => {
        cacheReads += 1;
        return new Response('<h1>Stale mobile player shell</h1>', {
          headers: { 'content-type': 'text/html' },
        });
      },
    },
    self: {
      location: { origin: 'https://chummer.run' },
      addEventListener: (name: string, listener: (event: FetchEventFixture) => void) => {
        listeners.set(name, listener);
      },
    },
  });

  runInContext(readFileSync(serviceWorkerPath, 'utf8'), context, {
    filename: serviceWorkerPath,
  });

  const fetchListener = listeners.get('fetch');
  if (!fetchListener) {
    throw new Error('service worker did not register its fetch listener');
  }

  return {
    cacheReads: () => cacheReads,
    async navigate(pathname: string) {
      let responsePromise: Promise<Response> | undefined;
      fetchListener({
        request: {
          method: 'GET',
          mode: 'navigate',
          destination: 'document',
          url: `https://chummer.run${pathname}`,
        },
        respondWith: (response) => {
          responsePromise = Promise.resolve(response);
        },
        waitUntil: () => undefined,
      });
      if (!responsePromise) {
        throw new Error(`service worker did not handle navigation to ${pathname}`);
      }
      return responsePromise;
    },
    async request(pathname: string) {
      let responsePromise: Promise<Response> | undefined;
      fetchListener({
        request: {
          method: 'GET',
          mode: 'cors',
          destination: '',
          url: `https://chummer.run${pathname}`,
        },
        respondWith: (response) => {
          responsePromise = Promise.resolve(response);
        },
        waitUntil: () => undefined,
      });
      if (!responsePromise) {
        throw new Error(`service worker did not handle request to ${pathname}`);
      }
      return responsePromise;
    },
  };
}

test('offline downloads and private navigations render honest accessible states', async ({ page }) => {
  const worker = createOfflineWorkerHarness();

  const downloads = await worker.navigate('/downloads');
  expect(downloads.status).toBe(503);
  expect(downloads.headers.get('content-type')).toBe('text/html; charset=utf-8');
  expect(downloads.headers.get('cache-control')).toBe('no-store');
  const downloadsHtml = await downloads.text();
  expect(downloadsHtml).toContain("Downloads aren't available offline");
  expect(downloadsHtml).toContain('does not show an older cached release as if it were current');
  expect(downloadsHtml).not.toContain('Stale mobile player shell');
  expect(worker.cacheReads()).toBe(0);

  await page.setContent(downloadsHtml);
  await expect(page.getByRole('heading', { name: "Downloads aren't available offline" })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Reconnect before checking the current release');

  const billing = await worker.navigate('/account/billing');
  expect(billing.status).toBe(503);
  expect(billing.headers.get('cache-control')).toBe('no-store');
  const billingHtml = await billing.text();
  expect(billingHtml).toContain("Billing isn't available offline");
  expect(billingHtml).toContain('Billing and account details are never replayed from an offline cache');

  const account = await worker.navigate('/account');
  expect(account.status).toBe(503);
  const accountHtml = await account.text();
  expect(accountHtml).toContain("Your account isn't available offline");
  expect(accountHtml).toContain('Private account details are never replayed from an offline cache');
});

test('offline API requests retain machine-readable problem details', async () => {
  const worker = createOfflineWorkerHarness();
  const response = await worker.request('/api/v1/accounts/me/profile');

  expect(response.status).toBe(503);
  expect(response.headers.get('content-type')).toBe('application/problem+json');
  expect(response.headers.get('cache-control')).toBe('no-store');
  await expect(response.json()).resolves.toEqual(expect.objectContaining({
    error: 'play_public_route_network_unavailable',
  }));
});
