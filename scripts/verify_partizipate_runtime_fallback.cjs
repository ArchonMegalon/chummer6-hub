#!/usr/bin/env node
'use strict';

const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const HOSTED_BOARD_SHELL_VISIBLE_BUDGET_MS = 6000;
const HOSTED_BOARD_DETAIL_FETCH_BUDGET_MS = 4000;

const args = process.argv.slice(2);
let baseUrl = process.env.CHUMMER_PUBLIC_BASE_URL || 'https://chummer.run';
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === '--base-url' && args[index + 1]) {
    baseUrl = args[index + 1];
    index += 1;
  }
}

baseUrl = baseUrl.replace(/\/+$/, '');

const defaultUserAgent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36';

async function navigateLenient(page, url, preferredState = 'domcontentloaded') {
  try {
    return await page.goto(url, { waitUntil: preferredState });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!message.includes('Timeout')) {
      throw error;
    }

    const fallback = await page.goto(url, { waitUntil: 'commit', timeout: 15000 });
    await page.locator('body').waitFor({ state: 'attached', timeout: 5000 }).catch(() => undefined);
    await page.waitForTimeout(750);
    return fallback;
  }
}

async function fetchText(url) {
  const startedAt = Date.now();
  const response = await fetch(url, {
    headers: {
      'user-agent': defaultUserAgent,
      'accept-language': 'en-US,en;q=0.9',
    },
    redirect: 'follow',
  });

  return {
    status: response.status,
    url: response.url,
    text: await response.text(),
    durationMs: Date.now() - startedAt,
  };
}

function stripNonVisibleHtml(html) {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<template\b[^>]*>[\s\S]*?<\/template>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

async function assertBoardShell(page, path) {
  const startedAt = Date.now();
  const response = await navigateLenient(page, `${baseUrl}${path}`, 'commit');
  assert(response, `${path} should return a response.`);
  assert.equal(response.status(), 200, `${path} should return 200.`);
  await page.getByRole('heading', { name: 'Participate' }).waitFor({ state: 'visible', timeout: 15000 });

  const text = await page.locator('body').innerText();
  assert.equal(/Participate/i.test(text), true, `${path} should render the first-party heading.`);
  assert.equal(/Public requests, clear bugs, useful ideas\./i.test(text), false, `${path} must not render the removed first-party summary.`);
  assert.equal(/Something went wrong|Could not load posts|Network error|support@productlift\.dev/i.test(text), false, `${path} must not show provider failure copy.`);
  assert.equal(/productlift\.dev/i.test(text), false, `${path} must not leak provider domains.`);

  const offline = /Board offline right now/i.test(text);
  const embeddedFrameCount = await page.locator('iframe[data-chummer-participate-frame]').count();
  assert.equal(embeddedFrameCount === 1 || offline, true, `${path} should expose either the same-origin board frame or the first-party offline fallback.`);
  if (!offline) {
    assert.equal(embeddedFrameCount, 1, `${path} should host the same-origin ProductLift board frame when the board is live.`);
  }

  const detailLink = page.locator('a[href^="/participate/board/"]').first();
  const detailHref = await detailLink.count() > 0
    ? await detailLink.getAttribute('href')
    : null;

  const visibleDurationMs = Date.now() - startedAt;
  assert(
    visibleDurationMs <= HOSTED_BOARD_SHELL_VISIBLE_BUDGET_MS,
    `${path} should render the first-party board shell within ${HOSTED_BOARD_SHELL_VISIBLE_BUDGET_MS} ms, got ${visibleDurationMs} ms.`,
  );

  return {
    offline,
    detailHref,
    visibleDurationMs,
  };
}

async function main() {
  const browser = await chromium.launch({
    channel: process.env.CHUMMER_PLAYWRIGHT_CHANNEL?.trim() || 'chromium',
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    userAgent: defaultUserAgent,
  });
  context.setDefaultTimeout(10000);
  context.setDefaultNavigationTimeout(15000);

  const page = await context.newPage();
  try {
    const wrapper = await assertBoardShell(page, '/participate');
    const board = await assertBoardShell(page, '/participate/board');
    const timings = {
      participateShellVisibleMs: wrapper.visibleDurationMs,
      participateBoardShellVisibleMs: board.visibleDurationMs,
      detailFetchMs: null,
    };

    let mode = wrapper.offline
      ? 'first_party_proxy_offline_fallback'
      : 'first_party_productlift_proxy';

    const detailHref = wrapper.detailHref || board.detailHref;
    if (detailHref) {
      const detailResponse = await fetchText(`${baseUrl}${detailHref}`);
      assert.equal(detailResponse.status, 200, `${detailHref} should return 200.`);
      assert(
        detailResponse.durationMs <= HOSTED_BOARD_DETAIL_FETCH_BUDGET_MS,
        `${detailHref} should return the first-party detail within ${HOSTED_BOARD_DETAIL_FETCH_BUDGET_MS} ms, got ${detailResponse.durationMs} ms.`,
      );
      const detailVisibleText = stripNonVisibleHtml(detailResponse.text);
      assert.equal(/Something went wrong|Could not load posts|Network error|support@productlift\.dev/i.test(detailVisibleText), false, 'vendor error copy must not be visible in the proxied request detail.');
      assert.equal(/productlift\.dev/i.test(detailResponse.text), false, 'first-party request detail must not leak provider domains.');
      assert.equal(/Back to requests/i.test(detailVisibleText), true, 'request detail should provide a first-party way back to the request list.');
      assert.equal(/Request detail/i.test(detailVisibleText), true, 'request detail should render a first-party detail heading.');
      assert.equal(/id="menubar"/i.test(detailResponse.text), false, 'provider menubar must stay hidden in the proxied request detail.');
      assert.equal(/id="global_search_mount"/i.test(detailResponse.text), false, 'provider search mount must stay hidden in the proxied request detail.');
      assert.equal(/data-chummer-board-skin|data-chummer-home-link-patch/i.test(detailResponse.text), false, 'request detail should not render the hosted board chrome anymore.');
      timings.detailFetchMs = detailResponse.durationMs;
      mode = `${mode}_with_first_party_detail`;
    }

    const framePage = await context.newPage();
    await navigateLenient(framePage, `${baseUrl}/participate/frame`, 'domcontentloaded');
    await framePage.waitForFunction(
      () => {
        const text = (document.body && document.body.innerText) || '';
        return /What do you want to see next\?|Board offline right now/i.test(text);
      },
      { timeout: 15000 },
    );
    assert.equal(/\/participate\/board\/?\?embed=1$/.test(framePage.url()), true, '/participate/frame should resolve to the embedded first-party board document.');
    assert.equal(await framePage.locator('iframe[data-chummer-participate-frame]').count(), 0, '/participate/frame should resolve directly to the embedded board document instead of nesting another frame.');
    const frameText = await framePage.locator('body').innerText();
    assert.equal(/What do you want to see next\?|Board offline right now/i.test(frameText), true, '/participate/frame should keep the request entry point visible.');
    await framePage.close();

    console.log(JSON.stringify({
      status: 'pass',
      url: `${baseUrl}/participate`,
      mode,
      timings,
    }));
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
