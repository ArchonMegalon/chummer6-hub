#!/usr/bin/env node
'use strict';

const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const baseUrl = (process.env.CHUMMER_HUB_PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8091').replace(/\/+$/, '');
const signupNext = '/downloads/install/avalonia-linux-x64-installer';
const bannedCopy = /\b(Read the linked detail|Read more|Learn more)\b/i;

async function expectVisible(page, selector, message) {
  await page.waitForSelector(selector, { state: 'visible' });
  const visible = await page.locator(selector).first().isVisible();
  assert.equal(visible, true, message || `Expected ${selector} to be visible.`);
}

async function assertNoBannedCopy(page, label) {
  const text = await page.locator('body').innerText();
  assert.equal(bannedCopy.test(text), false, `${label} rendered banned generic CTA copy.`);
}

async function gotoAndAssert(page, path, checks) {
  const response = await page.goto(`${baseUrl}${path}`, { waitUntil: 'domcontentloaded' });
  assert(response, `No response for ${path}`);
  assert.equal(response.status(), 200, `${path} should return 200.`);
  if (checks) {
    await checks();
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const uniqueEmail = `hub-e2e-${Date.now()}@example.com`;

  await gotoAndAssert(page, '/', async () => {
    await expectVisible(page, 'header[data-site-header]', 'Landing header should render once.');
    assert.equal(await page.locator('header[data-site-header]').count(), 1, 'Landing should only render one site header.');
    await expectVisible(page, 'text=Create account to get preview');
    await assertNoBannedCopy(page, 'Landing');
  });

  await page.goto(`${baseUrl}/home/access`, { waitUntil: 'domcontentloaded' });
  assert(page.url().includes('/login?next=%2Fhome%2Faccess'), 'Signed-out /home/access should preserve next.');

  await page.goto(`${baseUrl}/account/support`, { waitUntil: 'domcontentloaded' });
  assert(page.url().includes('/login?next=%2Faccount%2Fsupport'), 'Signed-out /account/support should preserve next.');

  await gotoAndAssert(page, '/downloads', async () => {
    await expectVisible(page, 'text=Create account to get preview');
    await expectVisible(page, 'text=Advanced download options');
    await assertNoBannedCopy(page, 'Downloads');
  });

  await page.goto(`${baseUrl}/signup?next=${encodeURIComponent(signupNext)}`, { waitUntil: 'domcontentloaded' });
  await expectVisible(page, 'input[name="email"]');
  await page.fill('input[name="email"]', uniqueEmail);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type="submit"]')
  ]);
  await expectVisible(page, 'text=Check your email');
  await expectVisible(page, 'text=Continue to Downloads');
  await assertNoBannedCopy(page, 'Signup confirmation');

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('link', { name: /Continue to Downloads/i }).click()
  ]);
  assert(page.url().includes('/downloads/install/avalonia-linux-x64-installer'), 'Signup callback should land on the signed-in handoff route.');
  await expectVisible(page, 'text=Claim code');

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: /Start download again/i }).click()
  ]);
  const suggestedFilename = download.suggestedFilename();
  assert(/avalonia.*(deb|AppImage|rpm|tar)/i.test(suggestedFilename), `Unexpected installer filename: ${suggestedFilename}`);

  await gotoAndAssert(page, '/home/access', async () => {
    await expectVisible(page, 'text=Access and return');
  });

  await gotoAndAssert(page, '/home/work', async () => {
    await expectVisible(page, 'text=Work and continuity');
  });

  await gotoAndAssert(page, '/account/access', async () => {
    await expectVisible(page, 'text=Devices & access');
  });

  await gotoAndAssert(page, '/account/support', async () => {
    await expectVisible(page, 'text=Support');
  });

  const installOptions = page.locator('#supportCaseInstallation option');
  if (await installOptions.count() > 1) {
    await page.selectOption('#supportCaseInstallation', { index: 1 });
    await expectVisible(page, '#supportCaseContextPreview');
  }

  await page.fill('#supportCaseTitle', 'Playwright support case');
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
  await expectVisible(page, 'text=Saved attachments');
  await expectVisible(page, 'text=playwright-support.log');

  const attachmentLinkCount = await page.locator('a', { hasText: 'Download' }).count();
  assert(attachmentLinkCount >= 1, 'Tracked support case should expose attachment downloads.');

  await assertNoBannedCopy(page, 'Tracked support case');

  await gotoAndAssert(page, '/roadmap/nexus-pan', async () => {
    await expectVisible(page, 'text=Why this horizon matters now');
    await expectVisible(page, 'text=Compare with current proof');
  });

  await gotoAndAssert(page, '/artifacts/current-preview-build', async () => {
    await expectVisible(page, 'text=Use and verify this proof');
    await expectVisible(page, 'text=Start from the live surface');
  });

  console.log(`hub playwright e2e completed against ${baseUrl}`);
  await browser.close();
})().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
