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

const checks = [
  {
    url: `${baseUrl}/`,
    assert: text =>
      text.includes('Chummer') &&
      text.includes('Stable') &&
      text.includes('Nightly') &&
      text.includes('What it does') &&
      requiredLandingLinks.every(link => text.includes(link))
  },
  {
    url: `${baseUrl}/downloads/`,
    assert: text =>
      text.includes('Install Chummer')
      && text.includes('Choose Stable or Nightly. Windows and Linux installers are published here.')
      && text.includes('Current stable build')
      && text.includes('Latest published build')
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
      text.includes('Open the right support case')
      && text.includes('Product bug')
  },
  {
    url: `${baseUrl}/what-is-chummer`,
    assert: text => text.includes('What Is Chummer?')
  },
  {
    url: `${baseUrl}/artifacts`,
    assert: text => text.includes('Artifacts')
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
    assert: (text, response) =>
      /\/downloads\/?$/.test(response.url)
      && text.includes('Install Chummer')
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
      && text.includes('Checks passed')
  }
];

(async () => {
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
      throw new Error(`Portal check failed: ${check.url} -> HTTP ${response.status}`);
    }

    let passed = false;
    try {
      passed = Boolean(check.assert(body, response));
    } catch (error) {
      throw new Error(`Portal check failed: ${check.url} -> assertion threw: ${error.message}`);
    }

    if (!passed) {
      throw new Error(`Portal check failed: ${check.url} -> assertion returned false`);
    }

    console.log(`ok: ${check.url}`);
  }

  console.log('portal E2E completed');
})().catch(error => {
  console.error(error.message);
  process.exit(1);
});
