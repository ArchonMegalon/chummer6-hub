#!/usr/bin/env node
'use strict';

const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const baseUrl = (process.env.CHUMMER_HUB_PLAYWRIGHT_BASE_URL || 'https://chummer.run').replace(/\/+$/, '');

async function expectVisible(page, selector, label) {
  await page.waitForSelector(selector, { state: 'visible' });
  const visible = await page.locator(selector).first().isVisible();
  assert.equal(visible, true, `${label} should be visible for ${selector}.`);
}

async function expectBodyText(page, needle, label) {
  const text = await page.locator('body').innerText();
  assert.equal(text.includes(needle), true, `${label} should include "${needle}".`);
}

async function expectLocatorText(locator, needle, label) {
  const text = await locator.innerText();
  assert.equal(text.includes(needle), true, `${label} should include "${needle}".`);
}

async function assertMobileNav(page, path, contentNeedle) {
  const label = `${path} mobile`;
  const response = await page.goto(`${baseUrl}${path}`, { waitUntil: 'domcontentloaded' });
  assert(response, `${label} should return a response.`);
  assert.equal(response.status(), 200, `${label} should return 200.`);

  await expectVisible(page, 'header[data-site-header]', label);
  await expectVisible(page, '[data-nav-toggle]', label);
  await expectBodyText(page, contentNeedle, label);

  const navToggle = page.locator('[data-nav-toggle]').first();
  assert.equal(await navToggle.getAttribute('aria-expanded'), 'false', `${label} mobile nav should start collapsed.`);

  await navToggle.click();
  await expectVisible(page, '[data-nav-sheet]', label);
  assert.equal(await navToggle.getAttribute('aria-expanded'), 'true', `${label} mobile nav should expand after the toggle opens.`);

  const navSheet = page.locator('[data-nav-sheet]').first();
  await expectLocatorText(navSheet, 'Downloads', label);
  await expectLocatorText(navSheet, 'Participate', label);
  await expectLocatorText(navSheet, 'Help', label);
  await expectLocatorText(navSheet, 'Contact', label);

  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelector('[data-nav-toggle]')?.getAttribute('aria-expanded') === 'false');
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    hasTouch: true,
    isMobile: true,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
  });
  const page = await context.newPage();

  try {
    await assertMobileNav(page, '/', 'Open downloads');
    await assertMobileNav(page, '/partizipate', 'Signed-in participation');
    console.log('mobile-nav: ok');
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
