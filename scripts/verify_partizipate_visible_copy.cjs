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
const url = `${baseUrl}/partizipate`;

const forbidden = [
  new RegExp('AI' + '-powered', 'i'),
  new RegExp('AI' + ' powered', 'i'),
  new RegExp('AI' + '-generated', 'i'),
  new RegExp('Artificial' + ' intelligence', 'i'),
  new RegExp('Automatically' + ' generate', 'i'),
  /ProductLift/i,
  /productlift\.dev/i,
  /\bLog in\b/i,
  /\bSign up\b/i,
  /\bSign in\b/i,
  /Chummer Participate/i,
  /Requests, votes, and shipped work\./i,
  /\bGathering votes\b/i,
  /\bAdd Feature or Bug\b/i,
  /\bShort title of your feedback/i,
  /\bDescribe your idea or bug/i,
  /-- Choose a category --/i,
  /Tell us how we could make Chummer6 more useful to you/i,
  /\bSend unique NPCs\b/i,
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('text=What should Chummer do next?', { timeout: 10000 });
    const text = await page.locator('body').innerText({ timeout: 10000 });
    const failures = forbidden
      .filter((pattern) => pattern.test(text))
      .map((pattern) => pattern.toString());

    if (failures.length > 0) {
      console.error(JSON.stringify({
        status: 'fail',
        url,
        failures,
        text: text.slice(0, 2000),
      }, null, 2));
      process.exitCode = 1;
      return;
    }

    console.log(JSON.stringify({
      status: 'pass',
      url,
      checked_forbidden_patterns: forbidden.length,
      title: await page.title(),
    }));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
