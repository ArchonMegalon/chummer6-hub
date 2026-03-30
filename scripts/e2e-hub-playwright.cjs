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

async function expectBodyText(page, needle, label) {
  const text = await page.locator('body').innerText();
  assert.equal(
    text.includes(needle),
    true,
    `${label} should render "${needle}" in visible body copy.\n\n${text.slice(0, 2400)}`
  );
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
  const uniqueEmail = `hub-e2e-${Date.now()}@example.com`;

  page.on('pageerror', (error) => {
    pageErrors.push(error?.stack || error?.message || String(error));
  });

  await gotoAndAssert(page, pageErrors, '/', async () => {
    await expectVisible(page, 'header[data-site-header]', 'Landing header should render once.');
    assert.equal(await page.locator('header[data-site-header]').count(), 1, 'Landing should only render one site header.');
    await expectVisible(page, 'text=Create account to get preview');
    await assertTextCount(page, 'Final pool 9', 1, 'Landing');
    await assertNoBannedCopy(page, 'Landing');
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
    await assertNoBannedCopy(page, 'Artifacts');
  });

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

  await gotoAndAssert(page, pageErrors, '/home/access', async () => {
    await expectVisible(page, 'text=Access and return');
    await expectVisible(page, 'text=Finish setup before you worry about devices and follow-up');
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
  });

  await gotoAndAssert(page, pageErrors, '/home/setup', async () => {
    await expectVisible(page, 'text=Finish the small setup flow, then come back to access and work');
  });

  await gotoAndAssert(page, pageErrors, '/downloads', async () => {
    await expectVisible(page, 'text=Recommended for this install');
    await expectVisible(page, 'text=Install posture');
    await expectMinimumCount(page, '.trust-pulse-trend__point', 2, 'Signed-in /downloads');
    await assertNoBannedCopy(page, 'Signed-in /downloads');
  });

  await gotoAndAssert(page, pageErrors, '/now', async () => {
    await expectVisible(page, 'text=Recommended for this install');
    await expectVisible(page, 'text=Install posture');
    await expectMinimumCount(page, '.trust-pulse-trend__point', 2, 'Signed-in /now');
    await assertNoBannedCopy(page, 'Signed-in /now');
  });

  await gotoAndAssert(page, pageErrors, '/help', async () => {
    await expectVisible(page, 'text=Recommended for this install');
    await expectVisible(page, 'text=Install posture');
    await expectMinimumCount(page, '.trust-pulse-trend__point', 2, 'Signed-in /help');
    await assertNoBannedCopy(page, 'Signed-in /help');
  });

  await gotoAndAssert(page, pageErrors, '/account', async () => {
    await expectVisible(page, 'text=Profile');
  });

  await gotoAndAssert(page, pageErrors, '/account/access', async () => {
    await expectVisible(page, 'text=Devices & access');
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

  await gotoAndAssert(page, pageErrors, '/account/settings', async () => {
    await expectVisible(page, 'text=More settings');
  });

  await gotoAndAssert(page, pageErrors, '/account/advanced', async () => {
    await expectVisible(page, 'text=Advanced account details');
  });

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

  await supportCaseTitleField.fill('Playwright support case');
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

  await gotoAndAssert(page, pageErrors, '/participate/codex', async () => {
    await expectVisible(page, 'text=Authorize in ChatGPT');
  });

  await gotoAndAssert(page, pageErrors, '/roadmap/nexus-pan', async () => {
    await expectVisible(page, 'text=Why this horizon matters now');
    await expectVisible(page, 'text=Compare with current proof');
  });

  await gotoAndAssert(page, pageErrors, '/artifacts/current-preview-build', async () => {
    await expectVisible(page, 'text=Use and verify this proof');
    await expectVisible(page, 'text=Available today');
    await expectVisible(page, 'text=Start from the live surface');
  });

  console.log(`hub playwright e2e completed against ${baseUrl}`);
  await browser.close();
})().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
