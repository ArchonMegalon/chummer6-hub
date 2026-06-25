#!/usr/bin/env node
'use strict';

const baseUrl = (process.env.CHUMMER_PORTAL_BASE_URL || 'http://127.0.0.1:8091').replace(/\/$/, '');
const publicHost = (process.env.CHUMMER_PORTAL_PUBLIC_HOST || '').trim();
const forwardedProto = (process.env.CHUMMER_PORTAL_FORWARDED_PROTO || '').trim();
const defaultHeaders = {};

if (publicHost) {
  defaultHeaders.Host = publicHost;
}
if (forwardedProto) {
  defaultHeaders['X-Forwarded-Proto'] = forwardedProto;
}

const requiredLandingLinks = [
  '/downloads',
  '/help',
  '/status',
  '/contact',
];

function hasBlazorBaseHref(html) {
  return /<base href="[^"]*\/blazor\/"/i.test(html);
}

const checks = [
  {
    url: `${baseUrl}/`,
    assert: text =>
      text.includes('Chummer') &&
      text.includes('Download Chummer') &&
      text.includes('Current public installer') &&
      text.includes('Watch 90 sec') &&
      requiredLandingLinks.every(link => text.includes(link))
  },
  {
    url: `${baseUrl}/downloads/`,
    assert: text =>
      text.includes('Install Chummer')
      && text.includes('Current public installer')
      && text.includes('Current build')
      && text.includes('Newest build')
      && text.includes('Windows')
      && text.includes('Linux')
  },
  {
    url: `${baseUrl}/downloads/releases.json`,
    assert: text => {
      const payload = JSON.parse(text);
      return typeof payload?.version === 'string'
        && typeof payload?.channel === 'string'
        && Array.isArray(payload?.downloads)
        && payload.downloads.length > 0;
    }
  },
  {
    url: `${baseUrl}/contact`,
    assert: text =>
      text.includes('Choose public feedback for ideas.')
      && text.includes('Product bug')
  },
  {
    url: `${baseUrl}/participate`,
    assert: text =>
      text.includes('Participate')
      && text.includes('participate-board')
      && text.includes('/participate/board')
      && !text.includes('Requests, votes, and shipped work.')
      && !text.includes('ProductLift')
  },
  {
    url: `${baseUrl}/partizipate`,
    assert: (text, response) =>
      /\/partizipate\/?$/.test(response.url)
      && text.includes('partizipate-board')
      && text.includes('Short requests, clear bugs, useful ideas.')
      && text.includes('Public requests')
      && !text.includes('participate-board')
      && !text.includes('data-chummer-board-skin')
      && !text.includes('cdn.productlift.dev')
      && !text.includes('media.productlift.dev')
      && !text.includes('Requests, votes, and shipped work.')
      && !text.includes('Use the right place')
      && !text.includes('Chummer Participate')
      && !text.includes('What do you want to see next?')
      && !text.includes('Something went wrong')
      && !text.includes('Could not load posts')
      && !text.includes('support@productlift.dev')
  },
  {
    url: `${baseUrl}/what-is-chummer`,
    assert: text => text.includes('What Is Chummer?')
  },
  {
    url: `${baseUrl}/artifacts`,
    assert: text =>
      text.includes('Detail gallery')
      && text.includes('Use this page for dossiers, recaps, and release details.')
  },
  {
    url: `${baseUrl}/faq`,
    assert: text => text.includes('FAQ')
  },
  {
    url: `${baseUrl}/hub`,
    assert: (text, response) =>
      response.url.endsWith('/login?next=%2Faccount')
      && text.includes('Sign in')
  },
  {
    url: `${baseUrl}/hub/`,
    assert: (text, response) =>
      response.url.endsWith('/login?next=%2Faccount')
      && text.includes('Sign in')
  },
  {
    url: `${baseUrl}/blazor/`,
    required: false,
    label: 'delegated-blazor',
    assert: (text, response) =>
      /\/blazor\/?$/.test(response.url)
      && (text.includes('Published browser surface') || text.includes('Published browser client'))
      && (text.includes('Launch browser workbench') || text.includes('Explore Chummer App'))
      && hasBlazorBaseHref(text)
  },
  {
    url: `${baseUrl}/avalonia/`,
    assert: (text, response) =>
      /\/downloads\/?$/.test(response.url)
      && text.includes('Install Chummer')
  },
  {
    url: `${baseUrl}/session/`,
    assert: (text, response) =>
      /\/play\/?$/.test(response.url)
      && text.includes('Player entry')
  },
  {
    url: `${baseUrl}/coach/`,
    assert: (text, response) =>
      /\/status\/?$/.test(response.url)
      && text.includes('Current release')
      && text.includes('Updated')
  }
];

(async () => {
  const delegatedWarnings = [];

  for (const check of checks) {
    const response = await fetch(check.url, {
      method: check.method ?? 'GET',
      headers: {
        ...defaultHeaders,
        ...(check.headers ?? {})
      },
      body: check.body
    });
    const body = await response.text();
    if (!response.ok) {
      if (check.required === false) {
        const message = `delegated-not-ready: ${check.label ?? check.url} -> HTTP ${response.status}`;
        delegatedWarnings.push(message);
        console.warn(message);
        continue;
      }

      throw new Error(`Portal check failed: ${check.url} -> HTTP ${response.status}`);
    }

    let passed = false;
    try {
      passed = Boolean(check.assert(body, response));
    } catch (error) {
      if (check.required === false) {
        const message = `delegated-not-ready: ${check.label ?? check.url} -> assertion threw: ${error.message}`;
        delegatedWarnings.push(message);
        console.warn(message);
        continue;
      }

      throw new Error(`Portal check failed: ${check.url} -> assertion threw: ${error.message}`);
    }

    if (!passed) {
      if (check.required === false) {
        const message = `delegated-not-ready: ${check.label ?? check.url} -> assertion returned false`;
        delegatedWarnings.push(message);
        console.warn(message);
        continue;
      }

      throw new Error(`Portal check failed: ${check.url} -> assertion returned false`);
    }

    console.log(`ok: ${check.url}`);
  }

  if (delegatedWarnings.length > 0) {
    console.warn(`portal E2E completed with delegated warnings: ${delegatedWarnings.length}`);
  }

  console.log('portal E2E completed');
})().catch(error => {
  console.error(error.message);
  process.exit(1);
});
