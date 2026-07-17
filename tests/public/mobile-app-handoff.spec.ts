import fs from 'node:fs';
import path from 'node:path';
import { expect, test } from 'playwright/test';

const siteScript = path.join(process.cwd(), 'Chummer.Run.Api/wwwroot/js/site.js');
const siteCss = path.join(process.cwd(), 'Chummer.Run.Api/wwwroot/css/site.css');
const handoffScript = path.join(process.cwd(), 'Chummer.Run.Api/wwwroot/js/mobile-app-handoff.js');
const landingView = fs.readFileSync(
  path.join(process.cwd(), 'Chummer.Run.Api/Views/PublicLanding/Landing.cshtml'),
  'utf8',
);
const origin = 'https://chummer.test';

const hashMigrationStart = landingView.indexOf('(function () {', landingView.indexOf('@section Scripts'));
const hashMigrationEnd = landingView.indexOf('})();', hashMigrationStart);
if (hashMigrationStart < 0 || hashMigrationEnd < 0) {
  throw new Error('Could not locate the landing hash-migration script.');
}
const hashMigrationScript = landingView.slice(hashMigrationStart, hashMigrationEnd + '})();'.length);

const handoffDialog = (id: string, route: string, title: string) => `
  <div id="${id}" role="dialog" aria-modal="true" aria-labelledby="${id}-title" data-mobile-app-handoff-dialog data-mobile-app-path="${route}" data-mobile-app-origin="${origin}" hidden>
    <div>
      <h2 id="${id}-title">${title}</h2>
      <button type="button" data-close-mobile-app-handoff>Close</button>
      <p data-mobile-app-suggestion role="status">Choose where to open the app.</p>
      <div data-mobile-app-qr-card tabindex="-1">
        <svg class="mobile-app-handoff__qr" data-mobile-app-qr role="img" aria-label="QR code for ${title}"></svg>
        <p data-mobile-app-qr-status hidden></p>
      </div>
      <label for="${id}-link">App link</label>
      <input id="${id}-link" data-mobile-app-link readonly>
      <button type="button" data-show-mobile-app-qr>Show QR / send to phone</button>
      <button type="button" data-copy-mobile-app-link>Copy link</button>
      <a href="${route}" data-mobile-app-open>Open on this device</a>
      <p data-mobile-app-copy-status hidden></p>
    </div>
  </div>`;

const landingFixture = `<!doctype html>
<html lang="en">
<body>
  <details open>
    <summary>Open Chummer</summary>
    <a href="/build" data-mobile-app-handoff="build-mobile-app-handoff">Build</a>
    <a href="/mobile/player" data-mobile-app-handoff="mobile-app-handoff">Play</a>
    <fieldset data-mobile-app-device-picker aria-describedby="mobile-app-device-status">
      <legend>Device handoff</legend>
      <label><input type="radio" name="mobile-app-device" value="auto" data-mobile-app-device-choice="auto" checked> Auto</label>
      <label><input type="radio" name="mobile-app-device" value="mobile" data-mobile-app-device-choice="mobile"> Mobile</label>
      <label><input type="radio" name="mobile-app-device" value="desktop" data-mobile-app-device-choice="desktop"> Desktop / QR</label>
    </fieldset>
    <p id="mobile-app-device-status" data-mobile-app-device-status role="status" aria-live="polite"></p>
  </details>
  ${handoffDialog('build-mobile-app-handoff', '/build', 'Open the character builder on your phone')}
  ${handoffDialog('mobile-app-handoff', '/mobile/player', 'Open the companion on your phone')}
</body>
</html>`;

async function loadFixture(
  page: import('playwright/test').Page,
  options: { userAgentDataMobile?: boolean | null } = {},
) {
  if (Object.hasOwn(options, 'userAgentDataMobile')) {
    await page.addInitScript((mobile) => {
      Object.defineProperty(navigator, 'userAgentData', {
        configurable: true,
        value: typeof mobile === 'boolean' ? { mobile } : undefined,
      });
    }, options.userAgentDataMobile);
  }
  await page.route(`${origin}/**`, async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: pathname === '/mobile/player'
        ? '<!doctype html><title>Chummer Play</title><h1>Mobile player</h1>'
        : pathname === '/build'
          ? '<!doctype html><title>Chummer Build</title><h1>Character builder</h1>'
          : landingFixture,
    });
  });
  await page.goto(`${origin}/`);
  await page.addStyleTag({ path: siteCss });
  await page.addScriptTag({ path: siteScript });
  await page.addScriptTag({ path: handoffScript });
  await expect(page.locator('[data-mobile-app-handoff-dialog][data-mobile-app-handoff-bound="true"]')).toHaveCount(2);
}

test('big-screen Build and Play open accessible deterministic same-origin QR handoffs', async ({ page }) => {
  await loadFixture(page);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          (window as typeof window & { copiedMobileLink?: string }).copiedMobileLink = value;
        },
      },
    });
  });

  const opener = page.getByRole('link', { name: 'Play' });
  const dialog = page.getByRole('dialog', { name: 'Open the companion on your phone' });
  await expect(page.getByLabel('Auto', { exact: true })).toBeChecked();
  await expect(page.locator('[data-mobile-app-device-status]')).toContainText('desktop browser');
  await expect(opener).toHaveAttribute('data-mobile-app-effective-device', 'desktop');
  await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
  await opener.click();

  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('data-mobile-app-suggested-action', 'qr');
  await expect(dialog.locator('[data-show-mobile-app-qr]')).toBeVisible();
  await expect(dialog.locator('[data-mobile-app-open]')).toBeVisible();
  await expect(page.locator('body')).toHaveClass(/dialog-open/);
  await expect.poll(() => opener.evaluate((node) => Boolean((node.closest('details') as HTMLElement | null)?.inert))).toBe(true);
  await expect.poll(() => page.locator('#build-mobile-app-handoff').evaluate((node) => (node as HTMLElement).inert)).toBe(true);
  await expect(dialog.locator('[data-mobile-app-link]')).toHaveValue(`${origin}/mobile/player`);
  await expect(dialog.locator('[data-mobile-app-open]')).toHaveAttribute('href', `${origin}/mobile/player`);
  await expect(dialog.locator('[data-mobile-app-qr]')).toHaveAttribute('data-qr-value', `${origin}/mobile/player`);
  await expect(dialog.locator('[data-mobile-app-qr] path')).toHaveCount(1);
  expect((await dialog.locator('[data-mobile-app-qr] path').getAttribute('d'))?.length).toBeGreaterThan(500);
  await expect(dialog.locator('[data-close-mobile-app-handoff]')).toBeFocused();

  await page.keyboard.press('Shift+Tab');
  await expect(dialog.locator('[data-mobile-app-open]')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(dialog.locator('[data-close-mobile-app-handoff]')).toBeFocused();

  await dialog.locator('[data-copy-mobile-app-link]').click();
  await expect.poll(() => page.evaluate(() => (window as typeof window & { copiedMobileLink?: string }).copiedMobileLink)).toBe(`${origin}/mobile/player`);
  await expect(dialog.locator('[data-mobile-app-copy-status]')).toContainText('Mobile link copied.');

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(page.locator('body')).not.toHaveClass(/dialog-open/);
  await expect.poll(() => opener.evaluate((node) => Boolean((node.closest('details') as HTMLElement | null)?.inert))).toBe(false);
  await expect.poll(() => page.locator('#build-mobile-app-handoff').evaluate((node) => (node as HTMLElement).inert)).toBe(false);
  await expect(opener).toBeFocused();

  const buildOpener = page.getByRole('link', { name: 'Build' });
  const buildDialog = page.getByRole('dialog', { name: 'Open the character builder on your phone' });
  await buildOpener.click();
  await expect(buildDialog).toBeVisible();
  await expect(buildDialog.locator('[data-mobile-app-link]')).toHaveValue(`${origin}/build`);
  await expect(buildDialog.locator('[data-mobile-app-open]')).toHaveAttribute('href', `${origin}/build`);
  await expect(buildDialog.locator('[data-mobile-app-qr]')).toHaveAttribute('data-qr-value', `${origin}/build`);
  await expect(buildDialog.locator('[data-mobile-app-qr] path')).toHaveCount(1);
  await expect(buildDialog.locator('[data-close-mobile-app-handoff]')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(buildDialog).toBeHidden();
  await expect(buildOpener).toBeFocused();

  const matricesMatch = await page.evaluate(() => {
    const api = (window as typeof window & {
      ChummerMobileAppHandoff: { buildQrMatrix: (value: string) => boolean[][] };
    }).ChummerMobileAppHandoff;
    const first = api.buildQrMatrix('https://chummer.run/mobile/player');
    const second = api.buildQrMatrix('https://chummer.run/mobile/player');
    return first.length === 29 && JSON.stringify(first) === JSON.stringify(second);
  });
  expect(matricesMatch).toBe(true);

  // Pending by design: add an independent scanner when one already exists in the workspace;
  // do not make the production encoder its own only oracle or add a decoder dependency blindly.
});

test('device resolver prioritizes explicit choice, then UA-CH, then coarse touch capability', async ({ page }) => {
  await loadFixture(page);
  const resolved = await page.evaluate(() => {
    const resolve = (window as typeof window & {
      ChummerMobileAppHandoff: {
        resolveEffectiveDevice: (
          preference: string,
          signals: {
            standalone: boolean;
            userAgentDataMobile: boolean | null;
            coarsePointer: boolean;
            maxTouchPoints: number;
          },
        ) => string;
      };
    }).ChummerMobileAppHandoff.resolveEffectiveDevice;
    return [
      resolve('desktop', { standalone: true, userAgentDataMobile: true, coarsePointer: true, maxTouchPoints: 5 }),
      resolve('mobile', { standalone: false, userAgentDataMobile: false, coarsePointer: false, maxTouchPoints: 0 }),
      resolve('auto', { standalone: true, userAgentDataMobile: false, coarsePointer: false, maxTouchPoints: 0 }),
      resolve('auto', { standalone: false, userAgentDataMobile: true, coarsePointer: false, maxTouchPoints: 0 }),
      resolve('auto', { standalone: false, userAgentDataMobile: false, coarsePointer: true, maxTouchPoints: 5 }),
      resolve('auto', { standalone: false, userAgentDataMobile: null, coarsePointer: true, maxTouchPoints: 5 }),
      resolve('auto', { standalone: false, userAgentDataMobile: null, coarsePointer: true, maxTouchPoints: 0 }),
    ];
  });
  expect(resolved).toEqual([
    'desktop',
    'mobile',
    'mobile',
    'mobile',
    'desktop',
    'mobile',
    'desktop',
  ]);
});

test('Auto mobile and persisted Mobile override navigate directly to clean install pages', async ({ page }) => {
  await loadFixture(page, { userAgentDataMobile: true });
  const autoPlay = page.getByRole('link', { name: 'Play' });
  await expect(autoPlay).toHaveAttribute('data-mobile-app-effective-device', 'mobile');
  await expect(autoPlay).not.toHaveAttribute('aria-haspopup', 'dialog');
  await Promise.all([
    page.waitForURL(`${origin}/mobile/player`),
    autoPlay.click(),
  ]);

  await loadFixture(page, { userAgentDataMobile: false });
  await page.getByLabel('Mobile', { exact: true }).check();
  await expect(page.locator('[data-mobile-app-device-status]')).toContainText('Mobile override');
  await expect.poll(() => page.evaluate(() =>
    localStorage.getItem('chummer.mobile-app-handoff.device.v1'))).toBe('mobile');
  await Promise.all([
    page.waitForURL(`${origin}/build`),
    page.getByRole('link', { name: 'Build' }).click(),
  ]);

  await loadFixture(page, { userAgentDataMobile: false });
  await expect(page.getByLabel('Mobile', { exact: true })).toBeChecked();
  await expect(page.getByRole('link', { name: 'Play' })).toHaveAttribute(
    'data-mobile-app-effective-device',
    'mobile',
  );
});

test('persisted Desktop / QR override remains available on a mobile browser', async ({ page }) => {
  await loadFixture(page, { userAgentDataMobile: true });
  await page.getByLabel('Desktop / QR', { exact: true }).check();
  await expect(page.locator('[data-mobile-app-device-status]')).toContainText('Desktop override');
  await expect.poll(() => page.evaluate(() =>
    localStorage.getItem('chummer.mobile-app-handoff.device.v1'))).toBe('desktop');

  const opener = page.getByRole('link', { name: 'Play' });
  await expect(opener).toHaveAttribute('data-mobile-app-effective-device', 'desktop');
  await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
  await opener.click();
  const dialog = page.getByRole('dialog', { name: 'Open the companion on your phone' });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[data-mobile-app-qr-card]')).toBeVisible();
  await expect(dialog.locator('[data-mobile-app-qr]')).toHaveAttribute(
    'data-qr-value',
    `${origin}/mobile/player`,
  );
});

test('handoff resolver rejects hostile, private, and non-install targets', async ({ page }) => {
  await loadFixture(page);
  const rejected = await page.evaluate((candidateTargets) => {
    const api = (window as typeof window & {
      ChummerMobileAppHandoff: { resolveTargetUrl: (value: string, origin: string) => string };
    }).ChummerMobileAppHandoff;
    return candidateTargets.map((candidate) => {
      try {
        api.resolveTargetUrl(candidate, 'https://chummer.test');
        return false;
      } catch {
        return true;
      }
    });
  }, [
    '/mobile/player?sessionId=private-session',
    '/build#private-fragment',
    '/api/play/session',
    'https://attacker.example/mobile/player',
    'https://user:secret@chummer.test/mobile/player',
  ]);
  expect(rejected).toEqual([true, true, true, true, true]);
});

test('forced colors preserve QR module contrast while leaving both fallbacks available', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' });
  await loadFixture(page);
  await page.getByRole('link', { name: 'Play' }).click();
  const dialog = page.getByRole('dialog', { name: 'Open the companion on your phone' });
  const qrStyle = await dialog.locator('[data-mobile-app-qr]').evaluate((node) => getComputedStyle(node).forcedColorAdjust);
  expect(qrStyle).toBe('none');
  await expect(dialog.locator('[data-mobile-app-open]')).toBeVisible();
  await expect(dialog.locator('[data-mobile-app-link]')).toHaveValue(`${origin}/mobile/player`);
});

test('legacy mobile anchors migrate without forwarding landing query data', async ({ page }) => {
  await page.route(`${origin}/**`, async (route) => {
    const url = new URL(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: url.pathname === '/'
        ? `<!doctype html><title>Landing</title><script>${hashMigrationScript}</script>`
        : '<!doctype html><title>Mobile player</title><h1>Mobile player</h1>',
    });
  });

  await page.goto(`${origin}/?sessionId=landing-selector&deviceId=landing-device&tracking=landing-campaign#turn-now-card`);

  await expect(page).toHaveURL(`${origin}/mobile/player#turn-now-card`);
});
