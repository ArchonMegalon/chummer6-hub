import { expect, test } from 'playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const publicOrigin = new URL(baseUrl).origin;
const mobileViewport = { width: 390, height: 844 };
const ignoredConsoleErrorFragments = [
  'Failed to load resource: net::ERR_NETWORK_CHANGED',
  'WebSocket closed with status code: 1006',
];

const safeErrorType = (error: unknown) => error instanceof Error && error.name ? error.name : 'UnknownError';

test('signed-out frontdoor exposes public Build and Play install handoffs and Play remains default-denied', async ({ browser }) => {
  test.setTimeout(180000);
  const page = await browser.newPage({ baseURL: baseUrl, viewport: mobileViewport });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'userAgentData', {
      configurable: true,
      value: { mobile: true },
    });
  });
  const pageErrors: string[] = [];
  const requestedUrls: string[] = [];
  page.on('request', (request) => requestedUrls.push(request.url()));
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (!ignoredConsoleErrorFragments.some((fragment) => text.includes(fragment))) {
      pageErrors.push(text);
    }
  });

  const proof = {
    contractName: 'chummer.frontdoor_mobile_install_boundary.v2',
    generated_at_utc: new Date().toISOString(),
    base_url: publicOrigin,
    viewport: mobileViewport,
  };
  let proofStage = 'landing-load';

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

    proofStage = 'public-handoffs';
    const hero = page.locator('[data-homepage-section="hero"]');
    await expect(hero).toContainText('Download Chummer');
    const openMenu = hero.locator('.minimal-open-chummer');
    await openMenu.locator('summary').click();
    await expect(openMenu).toHaveAttribute('open', '');

    const buildLink = openMenu.getByRole('link', { name: 'Build', exact: true });
    const playLink = openMenu.getByRole('link', { name: 'Play', exact: true });
    await expect(buildLink).toHaveAttribute('href', '/build');
    await expect(buildLink).toHaveAttribute('data-public-install-handoff', 'true');
    await expect(playLink).toHaveAttribute('href', '/mobile/player');
    await expect(playLink).toHaveAttribute('data-public-install-handoff', 'true');
    await expect(openMenu.locator('[data-disabled-target="/build"]')).toHaveCount(0);
    await expect(openMenu.locator('[data-disabled-target="/mobile/player"]')).toHaveCount(0);
    await expect(openMenu.getByLabel('Auto', { exact: true })).toBeChecked();
    await expect(openMenu.locator('[data-mobile-app-device-status]')).toContainText('mobile browser');
    await expect(buildLink).toHaveAttribute('data-mobile-app-effective-device', 'mobile');
    await expect(playLink).toHaveAttribute('data-mobile-app-effective-device', 'mobile');
    await expect(playLink).not.toHaveAttribute('aria-haspopup', 'dialog');

    const handoff = page.getByRole('dialog', { name: 'Open the companion on your phone' });
    await expect(handoff).toBeHidden();
    requestedUrls.length = 0;
    pageErrors.length = 0;
    proofStage = 'play-install-boundary';
    const [playerResponse] = await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      playLink.click(),
    ]);
    await expect(page).toHaveURL(new URL('/mobile/player', publicOrigin).toString());
    expect(playerResponse?.status()).toBe(200);
    expect(playerResponse?.headers()['cache-control']).toContain('no-store');
    expect(playerResponse?.headers()['referrer-policy']).toBe('no-referrer');

    const shell = page.locator('[data-play-surface="install-only"]');
    await expect(shell).toBeVisible();
    await expect(shell).toHaveAttribute('data-authority', 'none');
    await expect(shell).toHaveAttribute('data-live-session', 'unavailable');
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.player.webmanifest');
    await expect(page.locator('#turn-manual-install-help')).toContainText('Share, then Add to Home Screen');
    await expect(page.locator('#turn-manual-install-help')).toContainText('keep using this public install shell in the browser');

    for (const selector of [
      '[data-turn-root]',
      '#turn-companion-bootstrap',
      '[data-blazor-shell]',
      '.session-main',
      '.role-button',
      '#turn-share-owner-route-button',
      '#chummer-play-analytics-config',
    ]) {
      await expect(page.locator(selector), `private/live selector must be absent: ${selector}`).toHaveCount(0);
    }

    const browserState = await page.evaluate(() => ({
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage),
      overflowX: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth,
    }));
    const privateKeyFragments = ['session', 'grant', 'device', 'role', 'character', 'campaign', 'table'];
    const privateBrowserStateKeys = [...browserState.local, ...browserState.session].filter((key) =>
      privateKeyFragments.some((fragment) => key.toLowerCase().includes(fragment)),
    );
    expect(privateBrowserStateKeys.length).toBe(0);
    expect(browserState.overflowX).toBeLessThanOrEqual(1);

    const resourceUrls = await page.evaluate(() =>
      performance.getEntriesByType('resource').map((entry) => entry.name),
    );
    const allObservedUrls = [...requestedUrls, ...resourceUrls];
    expect(allObservedUrls.some((url) => url.includes('/api/play'))).toBe(false);
    expect(allObservedUrls.some((url) => url.includes('/_blazor'))).toBe(false);
    expect(allObservedUrls.some((url) => /[?&](sessionId|grant|deviceId|role)=/i.test(url))).toBe(false);
    expect(allObservedUrls.some((value) => {
      const url = new URL(value);
      return /(^|\.)(rybbit|plausible)\./i.test(url.hostname)
        || /^\/api\/(?:v\d+\/)?(analytics|events|telemetry|tracking)(?:[/?]|$)/i.test(url.pathname)
        || /^\/(analytics|events|telemetry|tracking)(?:[/?]|$)/i.test(url.pathname);
    })).toBe(false);
    expect(pageErrors.length).toBe(0);

    proofStage = 'complete';
    writeJsonArtifact('FRONTDOOR_MOBILE_LAUNCH.generated.json', {
      ...proof,
      status: 'pass',
      public_install_targets: ['/build', '/mobile/player'],
      device_routing: 'auto_ua_ch_mobile_direct',
      play_surface: 'install-only',
      play_authority: 'none',
      live_session: 'unavailable',
      pwa_manifest_path: '/manifest.player.webmanifest',
      live_turn_companion_shell: false,
      private_browser_state_keys: 0,
      play_api_requests: 0,
      blazor_circuit_requests: 0,
      analytics_requests: 0,
      private_query_requests: 0,
      page_errors: [],
    });
  } catch (error) {
    writeJsonArtifact('FRONTDOOR_MOBILE_LAUNCH.generated.json', {
      ...proof,
      status: 'fail',
      failure_stage: proofStage,
      failure_type: safeErrorType(error),
      live_turn_companion_shell: false,
    });
    throw error;
  } finally {
    await page.close({ runBeforeUnload: false }).catch(() => undefined);
  }
});

test('desktop Build and Play handoffs keep keyboard focus contained and expose 44px controls', async ({ browser }) => {
  test.setTimeout(180000);
  const page = await browser.newPage({
    baseURL: baseUrl,
    viewport: { width: 1366, height: 768 },
  });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'userAgentData', {
      configurable: true,
      value: { mobile: false },
    });
    Object.defineProperty(navigator, 'maxTouchPoints', {
      configurable: true,
      value: 0,
    });
  });

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const hero = page.locator('[data-homepage-section="hero"]');
    const openMenu = hero.locator('.minimal-open-chummer');
    const summary = openMenu.locator('summary');
    await summary.focus();
    await expect(summary).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(openMenu).toHaveAttribute('open', '');
    await openMenu.getByLabel('Desktop / QR', { exact: true }).check();

    for (const target of [
      {
        linkName: 'Build',
        dialogName: 'Open the character builder on your phone',
        openName: 'Open Build on this device',
      },
      {
        linkName: 'Play',
        dialogName: 'Open the companion on your phone',
        openName: 'Open Play on this device',
      },
    ]) {
      const opener = openMenu.getByRole('link', { name: target.linkName, exact: true });
      await expect(opener).toHaveAttribute('data-mobile-app-effective-device', 'desktop');
      await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
      await opener.focus();
      await page.keyboard.press('Enter');

      const dialog = page.getByRole('dialog', { name: target.dialogName });
      await expect(dialog).toBeVisible();
      expect(await hero.evaluate((node) => (node as HTMLElement).inert)).toBe(true);

      const closeButton = dialog.getByRole('button', { name: 'Close', exact: true });
      await expect(closeButton).toBeFocused();
      const focusStyle = await closeButton.evaluate((node) => {
        const style = getComputedStyle(node);
        return {
          color: style.outlineColor,
          style: style.outlineStyle,
          width: Number.parseFloat(style.outlineWidth),
        };
      });
      expect(focusStyle.style).not.toBe('none');
      expect(focusStyle.width).toBeGreaterThanOrEqual(3);
      expect(focusStyle.color).toBe('rgb(243, 234, 219)');

      const interactiveControls = dialog.locator('button, a[href], input:not([type="hidden"])');
      const controlSizes = await interactiveControls.evaluateAll((nodes) => nodes
        .filter((node) => {
          const element = node as HTMLElement;
          const style = getComputedStyle(element);
          return !element.hidden && style.display !== 'none' && style.visibility !== 'hidden';
        })
        .map((node) => {
          const element = node as HTMLElement;
          const bounds = element.getBoundingClientRect();
          return {
            label: element.getAttribute('aria-label') || element.textContent?.trim() || element.tagName,
            width: bounds.width,
            height: bounds.height,
          };
        }));
      expect(controlSizes.length).toBeGreaterThanOrEqual(5);
      for (const control of controlSizes) {
        expect(control.width, `${target.linkName} ${control.label} width`).toBeGreaterThanOrEqual(44);
        expect(control.height, `${target.linkName} ${control.label} height`).toBeGreaterThanOrEqual(44);
      }

      const qrToggle = dialog.locator('[data-show-mobile-app-qr]');
      const qrCard = dialog.locator('[data-mobile-app-qr-card]');
      await expect(qrToggle).toHaveRole('button');
      await expect(qrToggle).toHaveAccessibleName('Hide QR code');
      await qrToggle.focus();
      await page.keyboard.press('Enter');
      await expect(qrToggle).toBeFocused();
      await expect(qrToggle).toHaveAttribute('aria-expanded', 'false');
      await expect(qrToggle).toHaveAccessibleName('Show QR / send to phone');
      await expect(qrCard).toBeHidden();
      await page.keyboard.press('Enter');
      await expect(qrToggle).toBeFocused();
      await expect(qrToggle).toHaveAttribute('aria-expanded', 'true');
      await expect(qrToggle).toHaveAccessibleName('Hide QR code');
      await expect(qrCard).toBeVisible();

      await closeButton.focus();
      await page.keyboard.press('Shift+Tab');
      await expect(dialog.getByRole('link', { name: target.openName, exact: true })).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(closeButton).toBeFocused();
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(opener).toBeFocused();
      expect(await hero.evaluate((node) => (node as HTMLElement).inert)).toBe(false);
    }
  } finally {
    await page.close({ runBeforeUnload: false }).catch(() => undefined);
  }
});

test('homepage legacy mobile anchors drop all landing queries before entering the public player shell', async ({ browser }) => {
  test.setTimeout(120000);
  const page = await browser.newPage({ viewport: mobileViewport });
  const landingPath = path.resolve(process.cwd(), 'Chummer.Run.Api/Views/PublicLanding/Landing.cshtml');
  const landingSource = readFileSync(landingPath, 'utf8');
  const scriptStart = landingSource.indexOf('(function () {', landingSource.indexOf('@section Scripts'));
  const scriptEnd = landingSource.indexOf('})();', scriptStart);
  const proof = {
    contractName: 'chummer.frontdoor_mobile_anchor_redirect.v2',
    generated_at_utc: new Date().toISOString(),
    source_path: landingPath,
  };
  let proofStage = 'source-contract';

  try {
    expect(scriptStart).toBeGreaterThanOrEqual(0);
    expect(scriptEnd).toBeGreaterThan(scriptStart);
    const redirectScript = landingSource.slice(scriptStart, scriptEnd + '})();'.length);
    expect(redirectScript).toContain('const mobileTurnAnchorTargets = new Set([');
    expect(redirectScript).toContain('#turn-runsite-card');
    expect(redirectScript).toContain('const normalizedHash = window.location.hash.split("?")[0];');
    expect(redirectScript).toContain('window.location.replace(`/mobile/player${normalizedHash}`);');
    expect(redirectScript).not.toContain('window.location.search');

    await page.route('http://frontdoor.test/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Frontdoor redirect stub</title></head><body><main>Frontdoor redirect stub</main><script>${redirectScript}</script></body></html>`,
      });
    });

    proofStage = 'query-drop-navigation';
    await page.goto('http://frontdoor.test/?sessionId=test-only&grant=test-only&tracking=test-only#turn-runsite-card', {
      waitUntil: 'domcontentloaded',
    });
    await page.waitForURL('**/mobile/player#turn-runsite-card', { timeout: 60000 });
    const finalUrl = new URL(page.url());
    expect(finalUrl.pathname).toBe('/mobile/player');
    expect(finalUrl.search).toBe('');
    expect(finalUrl.hash).toBe('#turn-runsite-card');

    proofStage = 'complete';
    writeJsonArtifact('FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json', {
      ...proof,
      status: 'pass',
      entry_had_query: true,
      final_pathname: finalUrl.pathname,
      final_search: '',
      final_hash: finalUrl.hash,
    });
  } catch (error) {
    writeJsonArtifact('FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json', {
      ...proof,
      status: 'fail',
      failure_stage: proofStage,
      failure_type: safeErrorType(error),
    });
    throw error;
  } finally {
    await page.close({ runBeforeUnload: false }).catch(() => undefined);
  }
});
