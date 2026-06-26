#!/usr/bin/env node
'use strict';

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
  /chummer6\.productlift\.dev/i,
  /\bLog in\b/i,
  /\bSign up\b/i,
  /\bSign in\b/i,
  /\bGathering votes\b/i,
  /\bAdd Feature or Bug\b/i,
  /\bShort title of your feedback/i,
  /\bDescribe your idea or bug/i,
  /-- Choose a category --/i,
  /Tell us how we could make Chummer6 more useful to you/i,
  /\bSend unique NPCs\b/i,
];

const requiredHtml = [
  '<title>Participate - Chummer.run</title>',
  'data-chummer-board-skin',
];

const forbiddenHtml = [
  'partizipate-board__grid',
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
  const response = await fetch(url, {
    headers: {
      'User-Agent': 'chummer-partizipate-copy-gate/1',
      'Accept': 'text/html,application/xhtml+xml',
    },
  });
  const html = await response.text();
  const text = extractVisibleText(html);
  const title = (html.match(/<title>(.*?)<\/title>/i) || [])[1] || '';
  const failures = forbidden
    .filter((pattern) => pattern.test(text))
    .map((pattern) => pattern.toString());

  requiredHtml.forEach((needle) => {
    if (!html.includes(needle)) {
      failures.push(`missing-html:${needle}`);
    }
  });

  forbiddenHtml.forEach((needle) => {
    if (html.includes(needle)) {
      failures.push(`forbidden-html:${needle}`);
    }
  });

  if (!response.ok) {
    failures.push(`status:${response.status}`);
  }
  if (response.headers.has('set-cookie')) {
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
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
