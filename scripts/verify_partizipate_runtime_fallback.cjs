#!/usr/bin/env node
'use strict';

const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const args = process.argv.slice(2);
let baseUrl = process.env.CHUMMER_PUBLIC_BASE_URL || 'https://chummer.run';
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === '--base-url' && args[index + 1]) {
    baseUrl = args[index + 1];
    index += 1;
  }
}

baseUrl = baseUrl.replace(/\/+$/, '');

const boardErrorHtml = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Board</title></head>
<body>
  <main id="board-root">
    <h1>Something went wrong on our side.</h1>
    <p>Could not load posts.</p>
    <p>Network error while loading tab configuration.</p>
    <p>Please try again or contact support@productlift.dev</p>
  </main>
</body>
</html>`;

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
  });
  context.setDefaultTimeout(10000);
  context.setDefaultNavigationTimeout(15000);

  await context.route('**/participate/board**', route => route.fulfill({
    status: 200,
    contentType: 'text/html; charset=utf-8',
    body: boardErrorHtml,
  }));

  const page = await context.newPage();
  try {
    const response = await page.goto(`${baseUrl}/participate`, { waitUntil: 'domcontentloaded' });
    assert(response, '/participate should return a response.');
    assert.equal(response.status(), 200, '/participate should return 200.');

    const fallback = page.locator('[data-participate-board-fallback]');
    const frame = page.locator('#participate-board');

    await fallback.waitFor({ state: 'visible' });
    assert.equal(await fallback.isVisible(), true, 'first-party participate fallback should become visible.');
    assert.equal(await frame.isHidden(), true, 'embedded board should be hidden after vendor error copy appears.');

    const visibleText = await page.locator('body').innerText();
    assert.equal(visibleText.includes('The board is unavailable'), true, 'fallback should explain the state.');
    assert.equal(visibleText.includes('Try again shortly.'), true, 'fallback should give the next action.');
    assert.equal(/Something went wrong|Could not load posts|Network error|support@productlift\.dev/i.test(visibleText), false, 'vendor error copy must not be visible.');

    console.log(JSON.stringify({
      status: 'pass',
      url: `${baseUrl}/participate`,
      mode: 'runtime_fallback',
    }));
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
