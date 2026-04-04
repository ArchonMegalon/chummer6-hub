#!/usr/bin/env node
'use strict';

const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const baseUrl = (process.env.CHUMMER_HUB_PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8091').replace(/\/+$/, '');
const publicHost = (process.env.CHUMMER_HUB_PLAYWRIGHT_PUBLIC_HOST || '').trim();
const forwardedProto = (process.env.CHUMMER_HUB_PLAYWRIGHT_FORWARDED_PROTO || '').trim();
const isLocalReverseProxyMode = baseUrl.startsWith('http://') && forwardedProto.toLowerCase() === 'https';
const signupNext = '/downloads/install/avalonia-linux-x64-installer';
const bannedCopy = /\b(Read the linked detail|Read more|Learn more)\b/i;

async function expectVisible(page, selector, message) {
  await page.waitForSelector(selector, { state: 'visible' });
  const visible = await page.locator(selector).first().isVisible();
  assert.equal(visible, true, message || `Expected ${selector} to be visible.`);
}

async function expectMinimumCount(page, selector, minimum, label) {
  const count = await page.locator(selector).count();
  assert.equal(count >= minimum, true, `${label} should render at least ${minimum} match(es) for ${selector}, got ${count}.`);
}

async function assertNoPageErrors(page, pageErrors, label) {
  await page.waitForTimeout(50);
  if (pageErrors.length === 0) {
    return;
  }

  const errors = pageErrors.splice(0, pageErrors.length);
  assert.fail(`${label} produced client-side page errors:\n${errors.join('\n\n')}`);
}

async function assertNoBannedCopy(page, label) {
  const text = await page.locator('body').innerText();
  assert.equal(bannedCopy.test(text), false, `${label} rendered banned generic CTA copy.`);
}

async function assertTextCount(page, needle, expected, label) {
  const text = await page.locator('body').innerText();
  const matches = text.match(new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || [];
  assert.equal(matches.length, expected, `${label} should render "${needle}" ${expected} time(s), got ${matches.length}.`);
}

async function assertMinimumTextCount(page, needle, minimum, label) {
  const text = await page.locator('body').innerText();
  const matches = text.match(new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || [];
  assert.equal(matches.length >= minimum, true, `${label} should render "${needle}" at least ${minimum} time(s), got ${matches.length}.`);
}

async function expectBodyText(page, needle, label) {
  const text = await page.locator('body').innerText();
  assert.equal(
    text.includes(needle),
    true,
    `${label} should render "${needle}" in visible body copy.\n\n${text.slice(0, 2400)}`
  );
}

function isPublicCreatorPublicationPath(path) {
  return /\/artifacts\/(?:publications|creator)\//.test(path || '');
}

async function assertCreatorPublicationDetail(page, pageErrors, path, label) {
  await gotoAndAssert(page, pageErrors, path, async () => {
    const currentPath = new URL(page.url()).pathname;
    if (isPublicCreatorPublicationPath(path)) {
      assert(/\/artifacts\/publications\//.test(currentPath), `${label} should open the shared public publication route.`);
      await expectBodyText(page, 'Governed publication discovery', label);
      await expectBodyText(page, 'Public shared publication', label);
      await expectBodyText(page, 'Why this publication is live', label);
      await expectBodyText(page, 'Publication kind', label);
      await expectBodyText(page, 'Provenance', label);
      await expectBodyText(page, 'Trust', label);
      await expectBodyText(page, 'Discovery', label);
      await expectBodyText(page, 'Back to publication discovery', label);
      await expectBodyText(page, 'Open artifacts shelf', label);
    } else {
      assert(/\/account\/work\/publications\//.test(currentPath), `${label} should open the signed-in publication detail route.`);
      await expectBodyText(page, 'Publication status', label);
      await expectBodyText(page, 'Trust', label);
      await expectBodyText(page, 'Trust ranking', label);
      await expectBodyText(page, 'Publication kind', label);
      await expectBodyText(page, 'Discovery', label);
      await expectBodyText(page, 'Discoverable now', label);
      await expectBodyText(page, 'Status', label);
      await expectBodyText(page, 'Open build path for', label);
    }

    await assertNoBannedCopy(page, label);
  });
}

async function expandDetailsBySummary(page, summaryText, label) {
  const summary = page.locator('summary').filter({ hasText: summaryText }).first();
  if (await summary.count() === 0) {
    assert.fail(`${label} should render a details summary containing "${summaryText}".`);
  }

  const details = summary.locator('xpath=ancestor::details[1]');
  const isOpen = await details.evaluate((element) => element.hasAttribute('open'));
  if (!isOpen) {
    await summary.click();
  }
}

async function readFirstHref(page, selector, label) {
  const locator = page.locator(selector).first();
  if (await locator.count() === 0) {
    assert.fail(`${label} should render a link matching ${selector}.`);
  }

  const href = await locator.getAttribute('href');
  assert.equal(Boolean(href), true, `${label} should expose a non-empty href for ${selector}.`);
  return href;
}

async function readOptionalHref(page, selector) {
  const locator = page.locator(selector).first();
  if (await locator.count() === 0) {
    return null;
  }

  return locator.getAttribute('href');
}

async function readDefinitionValue(page, label, path) {
  const term = page.locator('dt').filter({ hasText: label }).first();
  if (await term.count() === 0) {
    assert.fail(`${path} should render a definition term containing "${label}".`);
  }

  const value = term.locator('xpath=following-sibling::dd[1]');
  if (await value.count() === 0) {
    assert.fail(`${path} should render a definition value for "${label}".`);
  }

  return (await value.innerText()).trim();
}

async function waitForParticipationPhase(page) {
  await page.waitForFunction(() => {
    const authorize = document.getElementById('authorizeState');
    const complete = document.getElementById('completeState');
    const unavailable = document.getElementById('unavailableState');
    return Boolean(
      (authorize && !authorize.hidden)
      || (complete && !complete.hidden)
      || (unavailable && !unavailable.hidden)
    );
  }, { timeout: 15000 });
}

function assertLoginRedirect(page, expectedNext, label) {
  const current = new URL(page.url());
  assert.equal(current.pathname, '/login', `${label} should redirect to /login.`);
  assert.equal(current.searchParams.get('next'), expectedNext, `${label} should preserve next.`);
}

async function gotoAndAssert(page, pageErrors, path, checks) {
  const response = await page.goto(`${baseUrl}${path}`, { waitUntil: 'domcontentloaded' });
  assert(response, `No response for ${path}`);
  assert.equal(response.status(), 200, `${path} should return 200.`);
  if (checks) {
    await checks();
  }
  await assertNoPageErrors(page, pageErrors, path);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const extraHTTPHeaders = {};
  if (publicHost) {
    extraHTTPHeaders.Host = publicHost;
  }
  if (forwardedProto) {
    extraHTTPHeaders['X-Forwarded-Proto'] = forwardedProto;
  }

  const context = await browser.newContext({
    acceptDownloads: true,
    extraHTTPHeaders
  });
  const page = await context.newPage();
  const pageErrors = [];
  const uniqueRunId = Date.now();
  const uniqueEmail = `hub-e2e-${uniqueRunId}@example.com`;
  const recoveryEmail = `hub-recovery-${uniqueRunId}@example.com`;
  const supportCaseTitle = `Playwright support case ${uniqueRunId}`;
  const profileDisplayName = `Profile Runner ${uniqueRunId}`;
  const profileHandle = `profile-runner-${uniqueRunId}`;
  const profileTimezone = 'America/New_York';
  let homeWorkspacePath;
  let homeBuildHandoffPath;
  let homeRulesPath;
  let homePublicationPath;
  let homeNextSessionPath;
  let homeAftermathPath;
  let homeDowntimePath;
  let homeCampaignMemoryPath;
  let homeRosterMovesPath;
  let homeMemberGuidancePath;
  let homeFirstPlayablePath;
  let homeLeagueRailPath;
  let homeSeasonBoardPath;
  let homeInviteRailPath;
  let homeSponsorRailPath;
  let publicCreatorPublicationPath;
  let accountPublicationBuildHandoffPath;
  let runDetailPath;
  let rulesDetailPath;

  page.on('pageerror', (error) => {
    pageErrors.push(error?.stack || error?.message || String(error));
  });

  await gotoAndAssert(page, pageErrors, '/', async () => {
    await expectVisible(page, 'header[data-site-header]', 'Landing header should render once.');
    assert.equal(await page.locator('header[data-site-header]').count(), 1, 'Landing should only render one site header.');
    await expectVisible(page, 'text=Create account to get preview');
    await assertTextCount(page, 'Final pool 9', 1, 'Landing');
    await expectVisible(page, 'text=Who can get it now');
    await expectVisible(page, 'text=Release proof');
    await expectVisible(page, 'text=Launch readiness');
    await expectVisible(page, 'text=Adoption health');
    await expectVisible(page, 'text=Closure health');
    await expectVisible(page, 'text=Progress trend');
    await expectVisible(page, 'text=Journey pulse');
    await expectVisible(page, 'text=Provider-route stewardship');
    await expectVisible(page, 'text=Current caution');
    await expectVisible(page, 'text=Open what works today');
    await expectVisible(page, 'text=Open progress');
    await expectMinimumCount(page, '.trust-pulse-trend__point', 2, 'Landing trust pulse');
    await assertNoBannedCopy(page, 'Landing');
  });

  await gotoAndAssert(page, pageErrors, '/what-is-chummer', async () => {
    await expectVisible(page, 'text=One product for rules truth, living dossiers, and session return.');
    await expectVisible(page, 'text=The short answer');
    await expectVisible(page, 'text=A Shadowrun companion with one front door');
    await expectVisible(page, 'text=Between build truth and table continuity');
    await expectVisible(page, 'text=Proof, release, and help stay attached');
    await expectVisible(page, 'text=Players, GMs, and creators on one rules truth');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/now"]', '/what-is-chummer now link'), '/now');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/downloads"]', '/what-is-chummer downloads link'), '/downloads');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/help"]', '/what-is-chummer help link'), '/help');
    await assertNoBannedCopy(page, '/what-is-chummer');
  });

  await gotoAndAssert(page, pageErrors, '/participate', async () => {
    await expectVisible(page, 'text=Choose how to participate');
    await expectVisible(page, 'text=Public feedback');
    await expectVisible(page, 'text=Signed-in participation');
    await expectBodyText(page, 'Report a problem without an account, then stop there unless you want tracked follow-up.', '/participate');
    await expectBodyText(page, 'Use the signed-in path when you want a tracked suggestion, beta follow-up, or a bounded contribution flow.', '/participate');
    assert.equal(await readFirstHref(page, 'a.editorial-strip__action[href="/contact#support-intake"]', '/participate support intake'), '/contact#support-intake');
    assert.equal(await readFirstHref(page, 'a.editorial-strip__action[href="/login?next=/participate/codex"]', '/participate guided contribution guest handoff'), '/login?next=/participate/codex');
    assert.equal(await readFirstHref(page, 'a.editorial-strip__action[href="/signup?next=/account/settings"]', '/participate beta signup handoff'), '/signup?next=/account/settings');
    await assertNoBannedCopy(page, '/participate');
  });

  await gotoAndAssert(page, pageErrors, '/faq', async () => {
    await expectVisible(page, 'text=Plain answers before you spend more time');
    await expectVisible(page, 'input[data-faq-filter]');
    await expectVisible(page, 'text=Search the FAQ');
    await expectVisible(page, 'text=Still stuck? Open support');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/downloads"]', '/faq downloads link'), '/downloads');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/contact#support-intake"]', '/faq support link'), '/contact#support-intake');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/now"]', '/faq now link'), '/now');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/contact#support-intake"]', '/faq footer support link'), '/contact#support-intake');
    await assertNoBannedCopy(page, '/faq');
  });

  await gotoAndAssert(page, pageErrors, '/privacy', async () => {
    await expectVisible(page, 'text=What Chummer stores, and what it does not');
    await expectVisible(page, 'text=Support, survey, and assistant data stay on a bounded clock');
    await expectVisible(page, 'text=What changed in this version');
    await expectVisible(page, 'text=Weekly trust pulse');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/downloads"]', '/privacy downloads link'), '/downloads');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/help"]', '/privacy help link'), '/help');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/contact#support-intake"]', '/privacy support link'), '/contact#support-intake');
    await assertNoBannedCopy(page, '/privacy');
  });

  await gotoAndAssert(page, pageErrors, '/terms', async () => {
    await expectVisible(page, 'text=Preview terms in plain language');
    await expectVisible(page, 'text=What changed in this version');
    await expectVisible(page, 'text=Create account to get preview');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/downloads"]', '/terms downloads link'), '/downloads');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/help"]', '/terms help link'), '/help');
    await assertNoBannedCopy(page, '/terms');
  });

  await gotoAndAssert(page, pageErrors, '/help', async () => {
    await expectVisible(page, 'text=Get help without guessing');
    await expectVisible(page, 'text=Fallback:');
    await expectVisible(page, 'text=Support, survey, and assistant data stay on a bounded clock');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/downloads"]', '/help downloads link'), '/downloads');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/faq"]', '/help faq link'), '/faq');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/contact#support-intake"]', '/help support link'), '/contact#support-intake');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/now"]', '/help now link'), '/now');
    await assertNoBannedCopy(page, '/help');
  });

  await page.goto(`${baseUrl}/home/access`, { waitUntil: 'domcontentloaded' });
  assertLoginRedirect(page, '/home/access', 'Signed-out /home/access');
  await assertNoPageErrors(page, pageErrors, 'Signed-out /home/access redirect');

  await page.goto(`${baseUrl}/account/support`, { waitUntil: 'domcontentloaded' });
  assertLoginRedirect(page, '/account/support', 'Signed-out /account/support');
  await assertNoPageErrors(page, pageErrors, 'Signed-out /account/support redirect');

  await page.goto(`${baseUrl}/participate/codex`, { waitUntil: 'domcontentloaded' });
  assertLoginRedirect(page, '/participate/codex', 'Signed-out /participate/codex');
  await assertNoPageErrors(page, pageErrors, 'Signed-out /participate/codex redirect');

  await gotoAndAssert(page, pageErrors, '/downloads', async () => {
    await expectVisible(page, 'text=Create account to get preview');
    await expectVisible(page, 'text=Advanced download options');
    await assertNoBannedCopy(page, 'Downloads');
  });

  await gotoAndAssert(page, pageErrors, '/contact', async () => {
    await expectVisible(page, 'text=Open a first-party support case');
  });
  await gotoAndAssert(
    page,
    pageErrors,
    '/contact?kind=install_help&title=Mobile%20follow-through%20needs%20grounded%20runtime&summary=Scene%20resume%20needs%20support%20review&detail=Session%3A%20session-redmond&sessionId=session-redmond&sceneId=scene-redmond&runtime=sr6.preview.v1&bundle=bundle-redmond',
    async () => {
      await expectVisible(page, 'text=Open a first-party support case');
      assert.equal(await page.locator('#supportKind').inputValue(), 'install_help', 'Prefilled contact route should preserve the support kind.');
      assert.equal(await page.locator('#supportTitle').inputValue(), 'Mobile follow-through needs grounded runtime', 'Prefilled contact route should preserve the support title.');
      assert.equal(await page.locator('#supportSummary').inputValue(), 'Scene resume needs support review', 'Prefilled contact route should preserve the support summary.');
      assert.equal(await page.locator('#supportDetail').inputValue(), 'Session: session-redmond', 'Prefilled contact route should preserve the support detail.');
      await page.getByText('Optional environment details').click();
      await expectVisible(page, 'text=Follow-through opened with session session-redmond · scene scene-redmond · runtime sr6.preview.v1 · bundle bundle-redmond.');
    });
  await gotoAndAssert(page, pageErrors, '/contact', async () => {
    await expectVisible(page, 'text=Open a first-party support case');
  });
  await page.selectOption('#supportKind', 'bug_report');
  await page.fill('#supportTitle', 'Guest support intake smoke');
  await page.fill('#supportSummary', 'Guest support submission should land on the first-party confirmation page.');
  await page.fill('#supportDetail', 'Browser harness is validating the public support intake route, reply-email requirement, and confirmation flow.');
  await page.fill('#supportReplyEmail', uniqueEmail);
  await page.getByText('Optional environment details').click();
  await page.fill('#supportPlatform', 'Linux');
  await page.fill('#supportVersion', 'preview-smoke');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('button', { name: /Submit support case/i }).click()
  ]);
  assert(/\/contact\/submitted\/support_case_/i.test(page.url()), 'Public contact form should redirect to the support confirmation route.');
  await expectVisible(page, 'text=Support case received');
  await expectVisible(page, 'text=Watch your reply email');
  await assertNoBannedCopy(page, 'Public support confirmation');
  await assertNoPageErrors(page, pageErrors, 'Public support confirmation');

  await gotoAndAssert(page, pageErrors, '/now', async () => {
    await expectVisible(page, 'text=What you can verify now');
    await expectVisible(page, 'text=Build, explain, and run with visible evidence');
    await expectVisible(page, 'text=Status guide');
    await assertNoBannedCopy(page, 'Now');
  });

  await gotoAndAssert(page, pageErrors, '/horizons', async () => {
    await expectVisible(page, 'text=Preparing next');
    await expectVisible(page, 'text=Designing in public');
    await expectVisible(page, 'text=Research track');
    await expectVisible(page, 'text=Status guide');
    const bodyText = await page.locator('body').innerText();
    assert.equal(bodyText.includes('Research tracks'), false, 'Horizons should use the unified research-track label.');
    await assertNoBannedCopy(page, 'Horizons');
  });

  await gotoAndAssert(page, pageErrors, '/artifacts', async () => {
    await expectVisible(page, 'text=Current proof surfaces');
    await expectVisible(page, 'text=Preview in progress');
    await expectVisible(page, 'text=Status guide');
    await expectVisible(page, 'text=Governed publication discovery');
    await expectVisible(page, 'text=Published shared publications');
    await expectVisible(page, 'text=Compare at a glance');
    await expectVisible(page, 'text=How live publications differ');
    await expectVisible(page, 'text=Open public publication');
    publicCreatorPublicationPath = await readFirstHref(page, 'a[href*="/artifacts/publications/"]', '/artifacts');
    await assertNoBannedCopy(page, 'Artifacts');
  });
  await assertCreatorPublicationDetail(page, pageErrors, publicCreatorPublicationPath, '/artifacts -> public publication');

  await page.goto(`${baseUrl}/signup?next=${encodeURIComponent(signupNext)}`, { waitUntil: 'domcontentloaded' });
  await expectVisible(page, 'input[name="email"]');
  await page.fill('input[name="email"]', uniqueEmail);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type="submit"]')
  ]);
  await expectVisible(page, 'text=Check your email');
  await expectVisible(page, 'text=Magic link sent');
  await expectVisible(page, 'text=Open the verification link for Downloads');
  await assertNoBannedCopy(page, 'Signup confirmation');
  await assertNoPageErrors(page, pageErrors, 'Signup confirmation');

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('link', { name: /Open the verification link for Downloads/i }).click()
  ]);
  if (isLocalReverseProxyMode) {
    assertLoginRedirect(page, signupNext, 'Local reverse-proxied signup callback');
    await expectVisible(page, 'text=Sign in');
    await assertNoPageErrors(page, pageErrors, 'Local reverse-proxied signup callback');
    await browser.close();
    return;
  }

  assert(page.url().includes('/downloads/install/avalonia-linux-x64-installer'), 'Signup callback should land on the signed-in handoff route.');
  await expectVisible(page, 'text=Claim code');
  await assertNoPageErrors(page, pageErrors, 'Download handoff');

  const downloadRequest = page.waitForResponse((response) => {
    const url = response.url();
    return url.includes('/downloads/file/avalonia-linux-x64-installer') && response.status() === 200;
  });
  await page.getByRole('link', { name: /Start download again/i }).click();
  const downloadResponse = await downloadRequest;
  const contentDisposition = downloadResponse.headers()['content-disposition'] || '';
  assert(/avalonia.*(deb|appimage|rpm|tar)/i.test(contentDisposition), `Unexpected installer response headers: ${contentDisposition}`);

  await gotoAndAssert(page, pageErrors, '/home', async () => {
    await expectVisible(page, 'text=Welcome back');
    await expectBodyText(page, 'Use the current preview', '/home');
    await expectBodyText(page, 'Keep this copy connected', '/home');
    await expandDetailsBySummary(page, 'Build, explain, and next step', '/home');
    await expectBodyText(page, 'What changed for me', '/home');
    await expectBodyText(page, 'Open shared campaign view', '/home');
    await expectBodyText(page, 'Open current release', '/home');
  });

  await gotoAndAssert(page, pageErrors, '/home/access', async () => {
    await expectVisible(page, 'text=Access and return');
    await expectVisible(page, 'text=Finish setup before you worry about devices and follow-up');
    await expectBodyText(page, 'Release and device state', '/home/access');
    await expandDetailsBySummary(page, 'Release and device state', '/home/access');
    await expectBodyText(page, 'Open current release', '/home/access');
    await expectBodyText(page, 'Open Devices & access', '/home/access');
    await expectBodyText(page, 'Open what works today', '/home/access');
    const bodyText = await page.locator('body').innerText();
    assert.equal(bodyText.includes('Need product proof before you act?'), false, '/home/access should use the calmer proof follow-through note.');
  });

  await gotoAndAssert(page, pageErrors, '/home/work', async () => {
    await expectVisible(page, 'text=Work');
    await expectVisible(page, 'text=Finish setup before the work surfaces try to carry too much');
    await expectBodyText(page, 'What changed for me', '/home/work');
    await expectBodyText(page, 'Aftermath recap', '/home/work');
    await expectBodyText(page, 'Safehouse / travel mode', '/home/work');
    await expectBodyText(page, 'GM prep', '/home/work');
    homeWorkspacePath = await readFirstHref(page, 'a[href*="/account/work/workspaces/"]', '/home/work');
    homeBuildHandoffPath = await readFirstHref(page, 'a[href*="/account/work/build-handoffs/"]', '/home/work');
    homeRulesPath = await readFirstHref(page, 'a[href*="/account/work/rules/"]', '/home/work');
    homePublicationPath = await readFirstHref(page, 'a[href*="/artifacts/publications/"], a[href*="/account/work/publications/"]', '/home/work');
    homeNextSessionPath = await readFirstHref(page, 'a[href*="#selected-next-session-carry-forward"]', '/home/work');
    homeAftermathPath = await readFirstHref(page, 'a[href*="#aftermath-packages"]', '/home/work');
    homeDowntimePath = await readFirstHref(page, 'a[href*="#selected-downtime-brief"]', '/home/work');
    homeCampaignMemoryPath = await readFirstHref(page, 'a[href*="#selected-campaign-memory"]', '/home/work');
    homeRosterMovesPath = await readFirstHref(page, 'a[href="/account/work#community-ops"]', '/home/work');
    homeMemberGuidancePath = await readFirstHref(page, 'a[href*="#community-op-guidance-"]', '/home/work');
    homeFirstPlayablePath = await readOptionalHref(page, 'a[href*="#selected-first-playable-session"]');
    homeLeagueRailPath = await readFirstHref(page, 'a[href*="#community-op-league-"]', '/home/work');
    homeSeasonBoardPath = await readFirstHref(page, 'a[href*="#community-op-board-"]', '/home/work');
    homeInviteRailPath = await readFirstHref(page, 'a[href*="#community-op-invites-"]', '/home/work');
    homeSponsorRailPath = await readFirstHref(page, 'a[href*="#community-op-sponsor-sessions-"]', '/home/work');
  });

  await gotoAndAssert(page, pageErrors, '/home/setup', async () => {
    await expectVisible(page, 'text=Finish the small setup flow, then come back to access and work');
    await expectVisible(page, '#openSetupButton');
  });
  await page.locator('#openSetupButton').click();
  await expectVisible(page, '#home-onboarding');
  await expectVisible(page, 'text=Finish the account basics');
  await expectVisible(page, 'text=Name and timezone');
  await page.locator('[data-onboarding-next]').click();
  await expectVisible(page, 'text=What you want from Chummer');
  await page.locator('[data-step-panel="2"] input[value="player"]').check();
  await page.locator('[data-onboarding-next]').click();
  await expectVisible(page, 'text=Backup sign-in and updates');
  await expectVisible(page, '[data-onboarding-submit]');
  await page.locator('#onboardingFollow').check();
  await page.locator('#onboardingBeta').check();
  await Promise.all([
    expectVisible(page, 'text=Setup saved.'),
    page.locator('[data-onboarding-submit]').click()
  ]);
  await page.waitForSelector('#home-onboarding', { state: 'hidden' });
  await assertNoBannedCopy(page, '/home/setup');
  await assertNoPageErrors(page, pageErrors, '/home/setup');

  await gotoAndAssert(page, pageErrors, '/home/setup', async () => {
    await expectVisible(page, '#openSetupButton');
  });

  await gotoAndAssert(page, pageErrors, homeWorkspacePath, async () => {
    await expectBodyText(page, 'What changed for me', '/home/work -> workspace detail');
    await expectBodyText(page, 'Support follow-through', '/home/work -> workspace detail');
    await expectBodyText(page, 'Artifact shelf posture', '/home/work -> workspace detail');
    await assertNoBannedCopy(page, '/home/work -> workspace detail');
  });

  await gotoAndAssert(page, pageErrors, homeBuildHandoffPath, async () => {
    await expectBodyText(page, 'Build follow-through', '/home/work -> build detail');
    await expectBodyText(page, 'Variant', '/home/work -> build detail');
    await expectBodyText(page, 'Progression', '/home/work -> build detail');
    await assertNoBannedCopy(page, '/home/work -> build detail');
  });

  await gotoAndAssert(page, pageErrors, homeRulesPath, async () => {
    await expectBodyText(page, 'Grounded rule answer', '/home/work -> rules detail');
    await expectBodyText(page, 'Before', '/home/work -> rules detail');
    await expectBodyText(page, 'After', '/home/work -> rules detail');
    await expectBodyText(page, 'Provenance', '/home/work -> rules detail');
    await assertNoBannedCopy(page, '/home/work -> rules detail');
  });

  await assertCreatorPublicationDetail(page, pageErrors, homePublicationPath, '/home/work -> publication detail');

  await gotoAndAssert(page, pageErrors, homeNextSessionPath, async () => {
    assert.equal(new URL(page.url()).hash, '#selected-next-session-carry-forward', '/home/work next-session link should preserve the target anchor.');
    await expectBodyText(page, 'Next-session carry-forward', '/home/work -> next-session return');
    await expectBodyText(page, 'Carry-forward summary', '/home/work -> next-session return');
  });

  await gotoAndAssert(page, pageErrors, homeAftermathPath, async () => {
    assert.equal(new URL(page.url()).hash, '#aftermath-packages', '/home/work aftermath link should preserve the target anchor.');
    await expectBodyText(page, 'Aftermath and recap', '/home/work -> aftermath return');
    await expectBodyText(page, 'Recent aftermath recap packages', '/home/work -> aftermath return');
  });

  await gotoAndAssert(page, pageErrors, homeDowntimePath, async () => {
    assert.equal(new URL(page.url()).hash, '#selected-downtime-brief', '/home/work downtime link should preserve the target anchor.');
    await expectBodyText(page, 'Downtime brief', '/home/work -> downtime brief');
    await expectBodyText(page, 'Next-session return', '/home/work -> downtime brief');
  });

  await gotoAndAssert(page, pageErrors, homeCampaignMemoryPath, async () => {
    assert.equal(new URL(page.url()).hash, '#selected-campaign-memory', '/home/work campaign-memory link should preserve the target anchor.');
    await expectBodyText(page, 'Campaign memory', '/home/work -> campaign memory');
    await expectBodyText(page, 'Return lane', '/home/work -> campaign memory');
  });

  await gotoAndAssert(page, pageErrors, homeRosterMovesPath, async () => {
    assert.equal(new URL(page.url()).hash, '#community-ops', '/home/work roster-moves link should preserve the target anchor.');
    await expectBodyText(page, 'Teams & permissions', '/home/work -> roster moves');
    await expectBodyText(page, 'Recent governed roster moves', '/home/work -> roster moves');
  });

  await gotoAndAssert(page, pageErrors, homeMemberGuidancePath, async () => {
    assert.equal(new URL(page.url()).hash.startsWith('#community-op-guidance-'), true, '/home/work member-guidance link should preserve the target anchor.');
    await expectBodyText(page, 'Member guidance rail', '/home/work -> member guidance');
    await expectBodyText(page, 'Current preview posture', '/home/work -> member guidance');
  });

  if (homeFirstPlayablePath) {
    await gotoAndAssert(page, pageErrors, homeFirstPlayablePath, async () => {
      assert.equal(new URL(page.url()).hash, '#selected-first-playable-session', '/home/work first-playable link should preserve the target anchor.');
      await expectBodyText(page, 'First playable session', '/home/work -> first playable');
      await expectBodyText(page, 'Playable kickoff', '/home/work -> first playable');
      await expectBodyText(page, 'Legal runner', '/home/work -> first playable');
      await expectBodyText(page, 'Understandable return', '/home/work -> first playable');
      await expectBodyText(page, 'Campaign-ready lane', '/home/work -> first playable');
    });
  }

  await gotoAndAssert(page, pageErrors, homeLeagueRailPath, async () => {
    assert.equal(new URL(page.url()).hash.startsWith('#community-op-league-'), true, '/home/work league-rail link should preserve the target anchor.');
    await expectBodyText(page, 'League / season operations', '/home/work -> league rail');
    await expectBodyText(page, 'Campaign return pulse', '/home/work -> league rail');
  });

  await gotoAndAssert(page, pageErrors, homeSeasonBoardPath, async () => {
    assert.equal(new URL(page.url()).hash.startsWith('#community-op-board-'), true, '/home/work season-board link should preserve the target anchor.');
    await expectBodyText(page, 'Season board', '/home/work -> season board');
    await expectBodyText(page, 'Open shared campaign view', '/home/work -> season board');
  });

  await gotoAndAssert(page, pageErrors, homeInviteRailPath, async () => {
    assert.equal(new URL(page.url()).hash.startsWith('#community-op-invites-'), true, '/home/work invite-rail link should preserve the target anchor.');
    await expectBodyText(page, 'Invite & sponsorship rail', '/home/work -> invite rail');
    await expectBodyText(page, 'Issue governed join code', '/home/work -> invite rail');
    await expectBodyText(page, 'Issue governed boost code', '/home/work -> invite rail');
  });

  await gotoAndAssert(page, pageErrors, homeSponsorRailPath, async () => {
    assert.equal(new URL(page.url()).hash.startsWith('#community-op-sponsor-sessions-'), true, '/home/work sponsor-rail link should preserve the target anchor.');
    await expectBodyText(page, 'Recent sponsor sessions', '/home/work -> sponsor rail');
  });

  await gotoAndAssert(page, pageErrors, '/downloads', async () => {
    await expectVisible(page, 'text=Recommended for this install');
    await expectVisible(page, 'text=Install posture');
    await assertMinimumTextCount(page, 'Adoption health', 2, 'Signed-in /downloads');
    await expectMinimumCount(page, '.trust-pulse-trend__point', 2, 'Signed-in /downloads');
    await assertNoBannedCopy(page, 'Signed-in /downloads');
  });

  await gotoAndAssert(page, pageErrors, '/now', async () => {
    await expectVisible(page, 'text=Recommended for this install');
    await expectVisible(page, 'text=Install posture');
    await assertMinimumTextCount(page, 'Adoption health', 2, 'Signed-in /now');
    await expectMinimumCount(page, '.trust-pulse-trend__point', 2, 'Signed-in /now');
    await assertNoBannedCopy(page, 'Signed-in /now');
  });

  await gotoAndAssert(page, pageErrors, '/help', async () => {
    await expectVisible(page, 'text=Recommended for this install');
    await expectVisible(page, 'text=Install posture');
    await assertMinimumTextCount(page, 'Adoption health', 2, 'Signed-in /help');
    await expectMinimumCount(page, '.trust-pulse-trend__point', 2, 'Signed-in /help');
    await assertNoBannedCopy(page, 'Signed-in /help');
  });

  await gotoAndAssert(page, pageErrors, '/account', async () => {
    await expectVisible(page, 'text=Profile');
    await expectBodyText(page, 'Keep the visible identity clear, stable, and easy to recognize.', '/account');
    await page.locator('#displayName').fill(profileDisplayName);
    await page.locator('#handle').fill(profileHandle);
    await page.locator('#timezone').fill(profileTimezone);
    await Promise.all([
      expectVisible(page, 'text=Profile saved.'),
      page.locator('#profileForm button[type="submit"]').click()
    ]);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await assertNoPageErrors(page, pageErrors, '/account reload');
    assert.equal(await page.locator('#displayName').inputValue(), profileDisplayName, '/account should persist the saved display name.');
    assert.equal(await page.locator('#handle').inputValue(), profileHandle, '/account should persist the saved handle.');
    assert.equal(await page.locator('#timezone').inputValue(), profileTimezone, '/account should persist the saved timezone.');

    await expandDetailsBySummary(page, 'Primary sign-in', '/account');
    await expectBodyText(page, 'Keep the daily sign-in path visible here without turning the profile route into a second full settings page.', '/account');
    await expectBodyText(page, 'Google', '/account');
    await expectBodyText(page, 'Email', '/account');

    await expandDetailsBySummary(page, 'Recovery email', '/account');
    await expectBodyText(page, 'Add a verified backup path so one sign-in method is never the whole story.', '/account');
    await page.locator('#recoveryEmail').fill(recoveryEmail);
    const recoveryStartResponsePromise = page.waitForResponse((response) => response.url().includes('/api/v1/accounts/me/links/email/start') && response.request().method() === 'POST');
    const recoveryPreviewNavigation = page.waitForURL((url) => new URL(url).pathname === '/auth/email/callback', { timeout: 10000 });
    await page.locator('#recoveryForm button[type="submit"]').click();
    const recoveryStartResponse = await recoveryStartResponsePromise;
    const recoveryPayload = await recoveryStartResponse.json();
    assert.equal(typeof recoveryPayload.previewHref === 'string' && recoveryPayload.previewHref.length > 0, true, '/account recovery flow should expose an inline preview verification link on the local proof lane.');
    await recoveryPreviewNavigation;
    await page.waitForURL((url) => new URL(url).pathname === '/account', { timeout: 10000 });
    await expectBodyText(page, 'Profile', '/account recovery return');
    await assertNoBannedCopy(page, '/account');
  });

  await gotoAndAssert(page, pageErrors, '/account/access', async () => {
    await expectVisible(page, 'text=Devices & access');
    await expectBodyText(page, 'Recent install handoffs', '/account/access');
    await expectBodyText(page, 'Cross-device recovery', '/account/access');
    await expectBodyText(page, 'Advanced device recovery', '/account/access');
    await expectBodyText(page, 'Open downloads', '/account/access');
    await expectBodyText(page, 'How install linking works', '/account/access');
    await expandDetailsBySummary(page, 'Finish on another device', '/account/access');
    await expectBodyText(page, 'use before', '/account/access finish-on-another-device');
    await expectVisible(page, 'text=Copy');
    await expandDetailsBySummary(page, 'Advanced device recovery', '/account/access');
    const offlineReturnSummary = page.locator('summary').filter({ hasText: 'Offline-ready return' }).first();
    if (await offlineReturnSummary.count()) {
      await expandDetailsBySummary(page, 'Offline-ready return', '/account/access');
      await expectBodyText(page, 'Offline-ready return', '/account/access');
    }
    await expandDetailsBySummary(page, 'What stays on this device', '/account/access');
    await expectBodyText(page, 'What stays on this device', '/account/access');
    const bodyText = await page.locator('body').innerText();
    assert.equal(bodyText.includes('grant_installation_'), false, '/account/access should not leak raw install grant ids.');
  });

  await gotoAndAssert(page, pageErrors, '/account/work', async () => {
    await expectVisible(page, 'text=Work');
    await expandDetailsBySummary(page, 'Work', '/account/work');
    await expandDetailsBySummary(page, 'Campaigns & dossiers', '/account/work');
    await expandDetailsBySummary(page, 'preview campaign', '/account/work');
    await expectBodyText(page, 'Shared campaign views', '/account/work');
    await expectBodyText(page, 'Build paths', '/account/work');
    await expectBodyText(page, 'Grounded rule answers', '/account/work');
    await expectBodyText(page, 'Creator publication shelf', '/account/work');
    await expectBodyText(page, 'Reference context', '/account/work');
    await expectBodyText(page, 'Active scene', '/account/work');
    await expectBodyText(page, 'Next safe action', '/account/work');
    await expandDetailsBySummary(page, 'Recent change packets', '/account/work');
    await expectBodyText(page, 'Recent change packets', '/account/work');
    await expectBodyText(page, 'Continuity snapshot', '/account/work');
    await expandDetailsBySummary(page, 'Build paths', '/account/work');
    await expectBodyText(page, 'Runtime:', '/account/work');
    await expectBodyText(page, 'Closure:', '/account/work');
    await expandDetailsBySummary(page, 'Grounded rule answers', '/account/work');
    await expectBodyText(page, 'Source:', '/account/work');
    await expandDetailsBySummary(page, 'Creator publication', '/account/work');
    await expectBodyText(page, 'Discovery:', '/account/work');
    runDetailPath = await readFirstHref(page, 'a[href*="/account/work/runs/"]', '/account/work');
    rulesDetailPath = await readFirstHref(page, 'a[href*="/account/work/rules/"]', '/account/work');
  });

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.locator('a[href*="/account/work/workspaces/"]').first().click()
  ]);
  assert(/\/account\/work\/workspaces\//.test(page.url()), 'Workspace detail route should open from the account work rail.');
  await expectBodyText(page, 'What changed for me', '/account/work/workspaces detail');
  await expectBodyText(page, 'Roster readiness and dossier freshness', '/account/work/workspaces detail');
  await expectBodyText(page, 'Move governed roster state', '/account/work/workspaces detail');
  await expectBodyText(page, 'Launch governed prep packet', '/account/work/workspaces detail');
  await expectBodyText(page, 'Stage travel prefetch', '/account/work/workspaces detail');
  await expectBodyText(page, 'Generate aftermath recap package', '/account/work/workspaces detail');
  await expectBodyText(page, 'Rule and continuity health', '/account/work/workspaces detail');
  await expectBodyText(page, 'GM prep library and travel mode', '/account/work/workspaces detail');
  await expectBodyText(page, 'Safehouse / travel mode', '/account/work/workspaces detail');
  await expectBodyText(page, 'Support follow-through', '/account/work/workspaces detail');
  await expandDetailsBySummary(page, 'Artifact shelf posture', '/account/work/workspaces detail');
  await expectBodyText(page, 'Audience:', '/account/work/workspaces detail');
  await expectBodyText(page, 'Ownership:', '/account/work/workspaces detail');
  await expectBodyText(page, 'Publication:', '/account/work/workspaces detail');
  await expectBodyText(page, 'Open publication status', '/account/work/workspaces detail');
  await assertNoBannedCopy(page, '/account/work/workspaces detail');
  await assertNoPageErrors(page, pageErrors, '/account/work/workspaces detail');

  await page.fill('#prepQuery', 'opposition');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('button', { name: 'Search prep library' }).click()
  ]);
  assert(/\/account\/work\/workspaces\/.+\?prepQuery=opposition/.test(page.url()), 'Workspace detail search should preserve the normalized prep query in the route.');
  await expectBodyText(page, 'Search results:', '/account/work/workspaces detail search');
  await expectBodyText(page, 'match(es) for "opposition"', '/account/work/workspaces detail search');
  await expectBodyText(page, 'Recent governed prep launches', '/account/work/workspaces detail search');
  await expectBodyText(page, 'Recent travel prefetch receipts', '/account/work/workspaces detail search');
  await expectBodyText(page, 'Recent aftermath recap packages', '/account/work/workspaces detail search');
  await expectBodyText(page, 'Next-session carry-forward', '/account/work/workspaces detail search');
  const workspaceSearchText = await page.locator('body').innerText();
  assert.equal(
    workspaceSearchText.includes('No governed prep packet matched that search yet.'),
    false,
    'Workspace detail search should return at least one governed prep packet for the opposition query.'
  );
  await assertNoBannedCopy(page, '/account/work/workspaces detail search');
  await assertNoPageErrors(page, pageErrors, '/account/work/workspaces detail search');

  await page.fill('#prepQuery', 'seasonops');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('button', { name: 'Search prep library' }).click()
  ]);
  assert(/\/account\/work\/workspaces\/.+\?prepQuery=seasonops/.test(page.url()), 'Workspace detail search should preserve the compact seasonops prep query in the route.');
  await expectBodyText(page, 'Search results:', '/account/work/workspaces detail season search');
  await expectBodyText(page, 'match(es) for "seasonops"', '/account/work/workspaces detail season search');
  await expectBodyText(page, 'Recent governed prep launches', '/account/work/workspaces detail season search');
  await expectBodyText(page, 'Recent travel prefetch receipts', '/account/work/workspaces detail season search');
  await expectBodyText(page, 'Recent aftermath recap packages', '/account/work/workspaces detail season search');
  await expectBodyText(page, 'Next-session carry-forward', '/account/work/workspaces detail season search');
  const workspaceSeasonSearchText = await page.locator('body').innerText();
  assert.equal(
    workspaceSeasonSearchText.includes('No governed prep packet matched that search yet.'),
    false,
    'Workspace detail search should return at least one governed prep packet for the compact seasonops query.'
  );
  await assertNoBannedCopy(page, '/account/work/workspaces detail season search');
  await assertNoPageErrors(page, pageErrors, '/account/work/workspaces detail season search');

  await page.fill('#prepQuery', 'heat');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('button', { name: 'Search prep library' }).click()
  ]);
  assert(/\/account\/work\/workspaces\/.+\?prepQuery=heat/.test(page.url()), 'Workspace detail search should preserve the heat continuity prep query in the route.');
  await expectBodyText(page, 'Search results:', '/account/work/workspaces detail heat search');
  await expectBodyText(page, 'match(es) for "heat"', '/account/work/workspaces detail heat search');
  await expectBodyText(page, 'Recent governed prep launches', '/account/work/workspaces detail heat search');
  await expectBodyText(page, 'Recent travel prefetch receipts', '/account/work/workspaces detail heat search');
  await expectBodyText(page, 'Recent aftermath recap packages', '/account/work/workspaces detail heat search');
  await expectBodyText(page, 'Next-session carry-forward', '/account/work/workspaces detail heat search');
  const workspaceHeatSearchText = await page.locator('body').innerText();
  assert.equal(
    workspaceHeatSearchText.includes('No governed prep packet matched that search yet.'),
    false,
    'Workspace detail search should return at least one governed prep packet for the heat continuity query.'
  );
  await assertNoBannedCopy(page, '/account/work/workspaces detail heat search');
  await assertNoPageErrors(page, pageErrors, '/account/work/workspaces detail heat search');

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.locator('a[href*="/account/work/publications/"]').first().click()
  ]);
  assert(/\/account\/work\/publications\//.test(page.url()), 'Publication detail route should open from the workspace artifact shelf.');
  await expectBodyText(page, 'Publication status', '/account/work/publications detail');
  await expectBodyText(page, 'Trust', '/account/work/publications detail');
  await expectBodyText(page, 'Trust ranking', '/account/work/publications detail');
  await expectBodyText(page, 'Discovery', '/account/work/publications detail');
  await expectBodyText(page, 'Discoverable now', '/account/work/publications detail');
  await expectBodyText(page, 'Status', '/account/work/publications detail');
  await expectBodyText(page, 'Open build path for', '/account/work/publications detail');
  accountPublicationBuildHandoffPath = await readFirstHref(page, 'a[href*="/account/work/build-handoffs/"]', '/account/work/publications detail');
  const accountPublicationPublicPath = await readOptionalHref(page, 'a[href*="/artifacts/publications/"]');
  await assertNoBannedCopy(page, '/account/work/publications detail');
  await assertNoPageErrors(page, pageErrors, '/account/work/publications detail');
  if (accountPublicationPublicPath) {
    await assertCreatorPublicationDetail(page, pageErrors, accountPublicationPublicPath, '/account/work/publications detail -> public publication');
  }

  await gotoAndAssert(page, pageErrors, accountPublicationBuildHandoffPath, async () => {
    assert(/\/account\/work\/build-handoffs\//.test(page.url()), 'Build handoff detail route should open from the publication detail route.');
    await expectBodyText(page, 'Build follow-through', '/account/work/build-handoffs detail');
    await expectBodyText(page, 'Variant', '/account/work/build-handoffs detail');
    await expectBodyText(page, 'Progression', '/account/work/build-handoffs detail');
    await expectBodyText(page, 'Next safe action', '/account/work/build-handoffs detail');
    await expectBodyText(page, 'Runtime', '/account/work/build-handoffs detail');
    await expectBodyText(page, 'Planner coverage', '/account/work/build-handoffs detail');
    await assertNoBannedCopy(page, '/account/work/build-handoffs detail');
  });

  await gotoAndAssert(page, pageErrors, runDetailPath, async () => {
    await expectBodyText(page, 'Run context', '/account/work/runs detail');
    await expectBodyText(page, 'Status', '/account/work/runs detail');
    await expectBodyText(page, 'Active scene', '/account/work/runs detail');
    await expectBodyText(page, 'Objectives', '/account/work/runs detail');
    await expectBodyText(page, 'Scenes', '/account/work/runs detail');
    await expectBodyText(page, 'Continuity:', '/account/work/runs detail');
    await assertNoBannedCopy(page, '/account/work/runs detail');
  });

  await gotoAndAssert(page, pageErrors, rulesDetailPath, async () => {
    await expectBodyText(page, 'Grounded rule answer', '/account/work/rules detail');
    await expectBodyText(page, 'Before', '/account/work/rules detail');
    await expectBodyText(page, 'After', '/account/work/rules detail');
    await expectBodyText(page, 'Provenance', '/account/work/rules detail');
    await expectBodyText(page, 'Evidence:', '/account/work/rules detail');
    await assertNoBannedCopy(page, '/account/work/rules detail');
  });

  await gotoAndAssert(page, pageErrors, '/account/settings', async () => {
    await expectVisible(page, 'text=More settings');
    await expandDetailsBySummary(page, 'Privacy', '/account/settings');
    await expectBodyText(page, 'Choose what stays visible while deeper identifiers remain tucked away.', '/account/settings');
    await expectBodyText(page, 'Visibility', '/account/settings');
    await expectBodyText(page, 'Recovery posture', '/account/settings');
    await expectBodyText(page, 'Provider-backed help', '/account/settings');

    await expandDetailsBySummary(page, 'Participation', '/account/settings');
    await expectBodyText(page, 'Tell Chummer which lanes matter to you and which updates you actually want to hear about.', '/account/settings');
    await expectBodyText(page, 'Follow roadmap updates', '/account/settings');
    await expectBodyText(page, 'Invite me when the right beta opens', '/account/settings');
    await page.locator('#followHorizons').check();
    await page.locator('#betaInterest').check();
    await Promise.all([
      expectVisible(page, 'text=Participation settings saved.'),
      page.locator('#experienceForm button[type="submit"]').click()
    ]);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await assertNoPageErrors(page, pageErrors, '/account/settings reload');
    await expandDetailsBySummary(page, 'Participation', '/account/settings reload');
    assert.equal(await page.locator('#followHorizons').isChecked(), true, '/account/settings should persist follow-horizons after save.');
    assert.equal(await page.locator('#betaInterest').isChecked(), true, '/account/settings should persist beta-interest after save.');

    await expandDetailsBySummary(page, 'Help and policy', '/account/settings');
    await expectBodyText(page, 'When you need support, privacy, or preview-use guidance, use the first-party pages instead of guessing.', '/account/settings');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/help"]', '/account/settings help link'), '/help');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/privacy"]', '/account/settings privacy link'), '/privacy');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/terms"]', '/account/settings terms link'), '/terms');
    assert.equal(await readFirstHref(page, 'a.button-like[href="/contact"]', '/account/settings contact link'), '/contact');
    await assertNoBannedCopy(page, '/account/settings');
  });

  await gotoAndAssert(page, pageErrors, '/account/advanced', async () => {
    await expectVisible(page, 'text=Advanced account details');
    await expectBodyText(page, 'Hub account id', '/account/advanced');
    await expectBodyText(page, 'Primary auth', '/account/advanced');
    await expectBodyText(page, 'Linked identities', '/account/advanced');
    await expectBodyText(page, 'Linked channels', '/account/advanced');
    await expectBodyText(page, 'Recovery posture', '/account/advanced');
    await expectBodyText(page, 'Follow horizons', '/account/advanced');
    await expectMinimumCount(page, '.detail-grid--account dd', 6, '/account/advanced detail values');
    assert.equal(parseInt(await readDefinitionValue(page, 'Linked identities', '/account/advanced'), 10) >= 2, true, '/account/advanced should reflect the new recovery-email identity after the verified preview round trip.');
    await assertNoBannedCopy(page, '/account/advanced');
  });

  await gotoAndAssert(page, pageErrors, '/account/support', async () => {
    await expectVisible(page, 'text=Support');
  });

  await expandDetailsBySummary(page, 'Need routing help first?', '/account/support');
  await page.fill('#supportAssistantQuery', 'How do I install or update the preview build?');
  await Promise.all([
    expectVisible(page, '#supportAssistantAnswer', '/account/support assistant answer'),
    expectVisible(page, '#supportAssistantActions', '/account/support assistant actions'),
    expectVisible(page, '#supportAssistantCitations', '/account/support assistant citations'),
    page.getByRole('button', { name: /Check guidance/i }).click()
  ]);
  await expectVisible(page, 'text=Grounded guidance loaded');
  await expectVisible(page, 'text=Open downloads');
  await expectVisible(page, 'text=Open support case');
  const assistantAnswer = await page.locator('#supportAssistantAnswer').innerText();
  assert(
    assistantAnswer.includes('first-party release and update docs match your question')
      || assistantAnswer.includes('first-party install and downloads docs cover this path'),
    `/account/support assistant should return grounded install/update guidance, got: ${assistantAnswer}`
  );
  await expectMinimumCount(page, '#supportAssistantCitations .settings-summary-row', 1, '/account/support assistant citations');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.locator('#supportAssistantActions a', { hasText: 'Open downloads' }).first().click()
  ]);
  assert.equal(new URL(page.url()).pathname, '/downloads', '/account/support assistant downloads action should route to /downloads.');
  await expectVisible(page, 'text=Advanced download options');
  await assertNoBannedCopy(page, '/downloads from support assistant');
  await assertNoPageErrors(page, pageErrors, '/downloads from support assistant');
  await gotoAndAssert(page, pageErrors, '/account/support', async () => {
    await expectVisible(page, 'text=Support');
  });
  await expandDetailsBySummary(page, 'Need routing help first?', '/account/support');
  await page.fill('#supportAssistantQuery', 'What is the safest build handoff before I export this dossier back into the campaign?');
  await Promise.all([
    expectVisible(page, '#supportAssistantAnswer', '/account/support build assistant answer'),
    expectVisible(page, '#supportAssistantActions', '/account/support build assistant actions'),
    expectVisible(page, '#supportAssistantCitations', '/account/support build assistant citations'),
    page.getByRole('button', { name: /Check guidance/i }).click()
  ]);
  await expectVisible(page, 'text=Grounded guidance loaded');
  await expectVisible(page, 'text=Open work');
  const buildAssistantAnswer = await page.locator('#supportAssistantAnswer').innerText();
  assert(
    buildAssistantAnswer.includes('grounded build or campaign follow-through path in your signed-in workspace'),
    `/account/support assistant should return grounded build-path guidance, got: ${buildAssistantAnswer}`
  );
  await expectMinimumCount(page, '#supportAssistantCitations .settings-summary-row', 1, '/account/support build assistant citations');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.locator('#supportAssistantActions a', { hasText: 'Open work' }).first().click()
  ]);
  assert.equal(new URL(page.url()).pathname, '/account/work', '/account/support assistant work action should route to /account/work.');
  await expectBodyText(page, 'Grounded rule answers', '/account/work from support assistant');
  await expectBodyText(page, 'Build follow-through', '/account/work from support assistant');
  await assertNoBannedCopy(page, '/account/work from support assistant');
  await assertNoPageErrors(page, pageErrors, '/account/work from support assistant');
  await gotoAndAssert(page, pageErrors, '/account/support', async () => {
    await expectVisible(page, 'text=Support');
  });
  await expandDetailsBySummary(page, 'Need routing help first?', '/account/support');
  await page.fill('#supportAssistantQuery', 'Why did the rule environment change for my campaign visibility posture?');
  await Promise.all([
    expectVisible(page, '#supportAssistantAnswer', '/account/support rules assistant answer'),
    expectVisible(page, '#supportAssistantActions', '/account/support rules assistant actions'),
    expectVisible(page, '#supportAssistantCitations', '/account/support rules assistant citations'),
    page.getByRole('button', { name: /Check guidance/i }).click()
  ]);
  await expectVisible(page, 'text=Grounded guidance loaded');
  await expectVisible(page, 'text=Open home');
  await expectMinimumCount(page, '#supportAssistantCitations .settings-summary-row', 1, '/account/support rules assistant citations');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.locator('#supportAssistantActions a', { hasText: 'Open home' }).first().click()
  ]);
  assert.equal(new URL(page.url()).pathname, '/home', '/account/support assistant home action should route to /home.');
  await expectBodyText(page, 'Welcome back', '/home from support assistant');
  await expectBodyText(page, 'Build, explain, and next step', '/home from support assistant');
  await expectBodyText(page, 'What changed for me', '/home from support assistant');
  await assertNoBannedCopy(page, '/home from support assistant');
  await assertNoPageErrors(page, pageErrors, '/home from support assistant');
  await gotoAndAssert(page, pageErrors, '/account/support', async () => {
    await expectVisible(page, 'text=Support');
  });

  const supportCaseTitleField = page.locator('#supportCaseTitle');
  if (await supportCaseTitleField.count() === 0) {
    const currentUrl = page.url();
    const bodyText = await page.locator('body').innerText();
    assert.fail(`/account/support should render the support form, but #supportCaseTitle was missing on ${currentUrl}.\n\n${bodyText.slice(0, 1200)}`);
  }

  const installOptions = page.locator('#supportCaseInstallation option');
  if (await installOptions.count() > 1) {
    await page.selectOption('#supportCaseInstallation', { index: 1 });
    await expectVisible(page, '#supportCaseContextPreview');
  }

  await supportCaseTitleField.fill(supportCaseTitle);
  await page.fill('#supportCaseSummary', 'Tracked support submission with attachment');
  await page.fill('#supportCaseDetail', 'Browser harness is validating tracked support submission, attachment persistence, and the signed-in return path.');
  await page.setInputFiles('#supportCaseAttachments', {
    name: 'playwright-support.log',
    mimeType: 'text/plain',
    buffer: Buffer.from('playwright support attachment\n')
  });

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('button', { name: /Submit support case/i }).click()
  ]);

  assert(/\/account\/support\/support_case_/i.test(page.url()), 'Support form should redirect to a tracked case route.');
  const trackedSupportCasePath = new URL(page.url()).pathname;
  await expectVisible(page, 'text=Tracked case');
  await expectVisible(page, 'text=Next safe action');
  await expectVisible(page, 'text=Closure');
  await expectVisible(page, 'text=Saved attachments');
  const savedAttachmentsSummary = page.locator('summary').filter({ hasText: 'Saved attachments' });
  if (await savedAttachmentsSummary.count()) {
    await savedAttachmentsSummary.first().click();
  }
  await expectVisible(page, 'text=playwright-support.log');
  await assertNoPageErrors(page, pageErrors, 'Tracked support case');

  const [attachmentDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('a', { hasText: 'Download' }).first().click()
  ]);
  assert(/playwright-support\.log$/i.test(attachmentDownload.suggestedFilename()), 'Tracked support case should download the uploaded attachment.');

  await assertNoBannedCopy(page, 'Tracked support case');

  await gotoAndAssert(page, pageErrors, '/account/support', async () => {
    await expectVisible(page, `text=${supportCaseTitle}`);
    await expectVisible(page, 'text=Need routing help first?');
  });
  await expandDetailsBySummary(page, 'Need routing help first?', '/account/support history');
  await page.fill('#supportAssistantQuery', supportCaseTitle);
  await Promise.all([
    expectVisible(page, '#supportAssistantAnswer', '/account/support case-truth assistant answer'),
    expectVisible(page, '#supportAssistantActions', '/account/support case-truth assistant actions'),
    expectVisible(page, '#supportAssistantCitations', '/account/support case-truth assistant citations'),
    page.getByRole('button', { name: /Check guidance/i }).click()
  ]);
  await expectVisible(page, 'text=Grounded guidance loaded');
  await expectVisible(page, 'text=Open support timeline');
  const caseTruthAnswer = await page.locator('#supportAssistantAnswer').innerText();
  assert(
    caseTruthAnswer.includes('I found') && caseTruthAnswer.includes(supportCaseTitle),
    `/account/support assistant should ground the query on the tracked case, got: ${caseTruthAnswer}`
  );
  await expectVisible(page, `#supportAssistantCitations text=${supportCaseTitle}`);
  const supportHistorySelector = `a[href="${trackedSupportCasePath}"]`;
  const supportHistoryHref = await readFirstHref(page, supportHistorySelector, '/account/support history');
  assert.equal(supportHistoryHref, trackedSupportCasePath, '/account/support history should keep the tracked case detail href.');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.locator(supportHistorySelector).first().click()
  ]);
  assert.equal(new URL(page.url()).pathname, trackedSupportCasePath, '/account/support history link should reopen the tracked case detail route.');
  await expectVisible(page, `text=${supportCaseTitle}`);
  await expectVisible(page, 'text=Next safe action');
  await assertNoBannedCopy(page, '/account/support history');

  await gotoAndAssert(page, pageErrors, '/participate/codex', async () => {
    await expectVisible(page, 'text=Help Chummer show its work.');
    await expectVisible(page, 'text=I want to participate');
    await expectVisible(page, 'text=Authorize in ChatGPT');
    await expectBodyText(page, 'One decision, one code, one clean handoff', '/participate/codex');
    await page.locator('#openParticipationWizardButton').click();
    await expectVisible(page, '#participationWizardDialog');
    await waitForParticipationPhase(page);

    const unavailableVisible = await page.locator('#unavailableState').isVisible().catch(() => false);
    if (unavailableVisible) {
      await expectVisible(page, 'text=Participation is unavailable right now');
      await expectVisible(page, 'text=Back to home');
      await expectVisible(page, 'text=Open account');
      await expectVisible(page, 'text=How it works');
      await assertNoBannedCopy(page, '/participate/codex unavailable');
      return;
    }

    const completeVisible = await page.locator('#completeState').isVisible().catch(() => false);
    if (completeVisible) {
      await expectVisible(page, "text=Thanks, you're set");
      await expectVisible(page, 'text=Back to home');
      await expectVisible(page, 'text=Open account');
      await assertNoBannedCopy(page, '/participate/codex complete');
      return;
    }

    await expectVisible(page, '#authorizeState');
    const participationHeading = await page.locator('#participationHeading').innerText();
    if (participationHeading.includes('Waiting for an available slot')) {
      await expectBodyText(page, 'All contribution slots are busy right now.', '/participate/codex queued');
      await expectBodyText(page, 'No code yet. Chummer is waiting for a contribution slot to open.', '/participate/codex queued');
    } else {
      assert.equal(participationHeading.includes('Authorize in ChatGPT'), true, `/participate/codex should reach the authorize heading or the queued heading, got: ${participationHeading}`);
      const code = await page.locator('#authorizationCode').innerText();
      assert.equal(code.startsWith('A fresh code will appear here after you start.'), false, '/participate/codex should render a fresh one-time code after starting the contribution lane.');
      assert.equal(await page.locator('#openAuthorizationLink').isEnabled(), true, '/participate/codex should enable the authorization link once a contribution lane exists.');
      await expectVisible(page, 'text=Keep this page open.');
    }

    await expectVisible(page, 'text=Technical details and controls');
    await expectVisible(page, 'text=Contribution id');
    await page.locator('#cancelContributionButton').click();
    await expectBodyText(page, 'This contribution lane has been stopped. You can start again whenever you want.', '/participate/codex stopped');
    await assertNoBannedCopy(page, '/participate/codex');
  });

  await gotoAndAssert(page, pageErrors, '/roadmap/nexus-pan', async () => {
    await expectVisible(page, 'text=Why this horizon matters now');
    await expectVisible(page, 'text=Current pain, expected unlock, and the live proof you should compare first');
    await expectVisible(page, 'text=Compare with current proof');
    await expectVisible(page, 'text=Need a decision instead?');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/now"]', '/roadmap/nexus-pan compare link'), '/now');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/contact#support-intake"]', '/roadmap/nexus-pan support link'), '/contact#support-intake');
    await assertNoBannedCopy(page, '/roadmap/nexus-pan');
  });

  await gotoAndAssert(page, pageErrors, '/artifacts/current-preview-build', async () => {
    await expectVisible(page, 'text=Use and verify this proof');
    await expectVisible(page, 'text=What this live artifact shows, who it helps, and what to check next');
    await expectVisible(page, 'text=Available today');
    await expectVisible(page, 'text=Start from the live surface');
    await expectVisible(page, 'text=Open current release');
    await expectVisible(page, 'text=Open support');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/now"]', '/artifacts/current-preview-build release link'), '/now');
    assert.equal(await readFirstHref(page, 'a.inline-link[href="/contact#support-intake"]', '/artifacts/current-preview-build support link'), '/contact#support-intake');
    await assertNoBannedCopy(page, '/artifacts/current-preview-build');
  });

  console.log(`hub playwright e2e completed against ${baseUrl}`);
  await browser.close();
})().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
