#!/usr/bin/env node
'use strict';

const { chromium } = require('playwright');

const args = process.argv.slice(2);
let baseUrl = process.env.CHUMMER_PUBLIC_BASE_URL || 'https://chummer.run';
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === '--base-url' && args[index + 1]) {
    baseUrl = args[index + 1];
    index += 1;
  }
}

baseUrl = baseUrl.replace(/\/+$/, '');
const url = `${baseUrl}/participate`;

const forbidden = [
  /ProductLift/i,
  /productlift\.dev/i,
  /chummer6\.productlift\.dev/i,
  /\bLog in\b/i,
  /\bSign up\b/i,
  /\bGathering votes\b/i,
  /\bAdd Feature or Bug\b/i,
  /\bShort title of your feedback/i,
  /\bDescribe your idea or bug/i,
  /-- Choose a category --/i,
  /Tell us how we could make Chummer6 more useful to you/i,
];

const requiredHtml = [
  'data-chummer-home-link-patch',
];

const forbiddenHtml = [
  'Requests, votes, and shipped work.',
];

function extractVisibleText(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<template[\s\S]*?<\/template>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage({
    viewport: { width: 1366, height: 768 },
    userAgent: 'chummer-partizipate-copy-gate/1',
  });
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForFunction(
    () => {
      const text = (document.body && document.body.innerText) || '';
      return /What should Chummer do next\?|Board offline right now/i.test(text);
    },
    { timeout: 15000 },
  );

  const html = await page.content();
  const text = ((await page.locator('body').innerText()).replace(/\s+/g, ' ').trim()) || extractVisibleText(html);
  const title = await page.title();
  const failures = forbidden
    .filter((pattern) => pattern.test(text))
    .map((pattern) => pattern.toString());

  requiredHtml.forEach((needle) => {
    if (!html.includes(needle)) {
      failures.push(`missing-html:${needle}`);
    }
  });

  if (!text.includes('What should Chummer do next?')) {
    failures.push('missing-text:What should Chummer do next?');
  }
if (!text.includes('Public requests, clear bugs, useful ideas.')) {
  failures.push('missing-text:Public requests, clear bugs, useful ideas.');
}
const hasEmbeddedBoard = html.includes('data-chummer-participate-frame');
const hasOfflineFallback = text.includes('Board offline right now');
if (hasEmbeddedBoard) {
  failures.push('unexpected-legacy-wrapper');
}
if (!text.includes('Public requests, clear bugs, useful ideas.') && !hasOfflineFallback) {
  failures.push('missing-participate-state:proxied-board-or-offline-fallback');
}

  forbiddenHtml.forEach((needle) => {
    if (html.includes(needle)) {
      failures.push(`forbidden-html:${needle}`);
    }
  });

  if (!response || !response.ok()) {
    failures.push(`status:${response ? response.status() : 'no-response'}`);
  }
  if (response.headers()['set-cookie']) {
    failures.push('forwarded-set-cookie');
  }
  if (/What do you want to see next/i.test(title) || /ProductLift/i.test(title)) {
    failures.push(`title:${title}`);
  }

  if (failures.length > 0) {
    console.error(JSON.stringify({
      status: 'fail',
      url,
      failures,
      text: text.slice(0, 2000),
      title,
    }, null, 2));
    await browser.close();
    process.exitCode = 1;
    return;
  }

  console.log(JSON.stringify({
    status: 'pass',
    url,
    checked_forbidden_patterns: forbidden.length,
    checked_required_html: requiredHtml.length,
    checked_forbidden_html: forbiddenHtml.length,
    title,
  }));
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
