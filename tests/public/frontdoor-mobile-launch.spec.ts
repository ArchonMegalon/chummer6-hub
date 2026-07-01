import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const mobileViewport = { width: 390, height: 844 };
const ignoredConsoleErrorFragments = [
  'Failed to load resource: net::ERR_NETWORK_CHANGED',
];

test('mobile homepage open-chummer menu gates Build and exposes Play', async ({ browser }) => {
  test.setTimeout(60000);
  const buildPage = await browser.newPage({ baseURL: baseUrl, viewport: mobileViewport });
  const pageErrors: string[] = [];
  buildPage.on('pageerror', (error) => pageErrors.push(error.message));
  buildPage.on('console', (message) => {
    if (message.type() === 'error') {
      const text = message.text();
      if (!ignoredConsoleErrorFragments.some((fragment) => text.includes(fragment))) {
        pageErrors.push(text);
      }
    }
  });
  await buildPage.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  const homepageMetrics = await buildPage.evaluate(() => ({
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    overflowX: Math.max(
      document.documentElement.scrollWidth,
      document.body.scrollWidth,
    ) - window.innerWidth,
  }));

  const hero = buildPage.locator('[data-homepage-section="hero"]');
  await expect(hero).toContainText('Download Chummer');

  const openMenu = hero.locator('.minimal-open-chummer');
  const openMenuSummary = openMenu.locator('summary');
  await expect(openMenuSummary).toContainText('Open Chummer');
  await openMenuSummary.click();
  await expect(openMenu).toHaveAttribute('open', '');

  const buildButton = openMenu.locator('button.site-open-chummer-menu__button', { hasText: 'Build' });
  const playButton = openMenu.locator('.site-open-chummer-menu__button[href="/mobile/player"]', { hasText: 'Play' });
  const accountLink = openMenu.getByRole('link', { name: 'Sign in first' });

  await expect(buildButton).toBeVisible();
  await expect(buildButton).toBeDisabled();
  await expect(playButton).toBeVisible();
  await expect(playButton).toHaveAttribute('href', '/mobile/player');
  await expect(accountLink).toBeVisible();
  const accountRoute = await accountLink.getAttribute('href');
  await expect(openMenu.locator('.site-open-chummer-menu__button[href="/build"]')).toHaveCount(0);
  await expect(openMenu.locator('button.site-open-chummer-menu__button', { hasText: 'Play' })).toHaveCount(0);
  await expect(openMenu.locator('.site-open-chummer-menu__button[href="/play"]')).toHaveCount(0);

  const playerUrl = `${baseUrl.replace(/\/$/, '')}/mobile/player`;
  const playerResponse = await buildPage.request.get(playerUrl, {
    headers: { 'User-Agent': 'Mozilla/5.0 ChummerFrontdoorMobileLaunch/1.0' },
    timeout: 90000,
  });
  const directPlayerStatus = playerResponse.status();
  const playerHtml = await playerResponse.text();
  const playerTitle = playerHtml.match(/<title>([^<]+)<\/title>/i)?.[1]?.trim() ?? '';
  const manifestHref = playerHtml.match(/<link[^>]+rel=["']manifest["'][^>]+href=["']([^"']+)["']/i)?.[1] ?? '';
  const liveTurnCompanionShell = playerHtml.includes('LIVE-SESSION TURN COMPANION')
    || playerTitle.includes('Chummer Mobile Turn Companion')
    || playerHtml.includes('data-turn-root');
  const playerProjectionShell = playerHtml.includes('Player entry')
    || playerHtml.includes('data-pwa-ledger-status')
    || playerHtml.includes('Chummer Mobile Turn Companion');
  const role = playerHtml.includes('data-role="Player"') ? 'Player' : null;
  const finalUrl = playerResponse.url();

  writeJsonArtifact('FRONTDOOR_MOBILE_LAUNCH.generated.json', {
    contractName: 'chummer.frontdoor_mobile_launch.v1',
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    viewport: mobileViewport,
    homepage_overflow_x: homepageMetrics.overflowX,
    account_route: accountRoute,
    play_route: '/mobile/player',
    direct_player_route: '/mobile/player',
    direct_player_http_status: directPlayerStatus,
    direct_player_title: playerTitle,
    final_url: finalUrl,
    pwa_role: role || 'Player',
    live_turn_companion_shell: liveTurnCompanionShell,
    pwa_manifest: manifestHref,
    gated_targets: ['Build'],
    public_targets: ['Play'],
    page_errors: pageErrors,
  });

  expect(homepageMetrics.viewportWidth).toBe(mobileViewport.width);
  expect(homepageMetrics.overflowX).toBeLessThanOrEqual(1);
  expect(directPlayerStatus).toBeGreaterThanOrEqual(200);
  expect(directPlayerStatus).toBeLessThan(500);
  expect(finalUrl).toContain('/mobile/player');
  expect(playerProjectionShell).toBe(true);
  expect(manifestHref || '').toBe('/manifest.player.webmanifest');
  expect(role || 'Player').toBe('Player');
  expect(pageErrors).toEqual([]);

  await buildPage.close();
});
