#!/usr/bin/env node
'use strict';

const baseUrl = (process.env.CHUMMER_PORTAL_BASE_URL || 'http://127.0.0.1:8091').replace(/\/$/, '');
const publicHost = (process.env.CHUMMER_PORTAL_PUBLIC_HOST || '').trim();
const forwardedProto = (process.env.CHUMMER_PORTAL_FORWARDED_PROTO || '').trim();
const requireBlazor = /^(1|true|yes|on)$/i.test((process.env.CHUMMER_PORTAL_REQUIRE_BLAZOR || '').trim());
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
];

function hasBlazorBaseHref(html) {
  return /<base href="[^"]*\/blazor\/"/i.test(html);
}

function isBlazorReady(text) {
  return (
    (text.includes('Published browser surface') || text.includes('Published browser client'))
    && (text.includes('Launch browser workbench') || text.includes('Explore Chummer App'))
    && hasBlazorBaseHref(text)
  );
}

function isBlazorFallback(text) {
  return (
    text.includes('Browser preview is not ready right now.')
    && text.includes('Download Chummer')
    && text.includes('href="/downloads"')
    && text.includes('href="/status"')
  );
}

function isGuestBillingSurface(text) {
  return (
    text.includes('Open Chummer')
    && text.includes('Email first. Google if you prefer.')
    && text.includes('Continue with email')
    && text.includes('Continue with Google')
    && !text.includes('Supporter is not open right now.')
    && !text.includes('Account settings')
    && !text.includes('Membership')
  );
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
      text.includes('Downloads')
      && text.includes('Main build for this browser')
      && text.includes('Stable')
      && text.includes('Nightly')
      && text.includes('Build from source')
      && text.includes('Download script')
  },
  {
    url: `${baseUrl}/help`,
    assert: text =>
      text.includes('What is wrong?')
      && text.includes('Pick the next step.')
      && text.includes('Install or update')
      && text.includes('Account recovery')
      && text.includes('Private support')
      && text.includes('Read the FAQ')
  },
  {
    url: `${baseUrl}/status`,
    assert: text =>
      text.includes('Updated')
      && text.includes('Windows and Linux downloads are live.')
      && text.includes('Downloads')
      && text.includes('Help')
      && !text.includes('Checks passed')
      && !text.includes('Released')
      && !text.includes('Build run-')
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
    url: `${baseUrl}/account`,
    assert: (text, response) =>
      (
        response.url.endsWith('/login?next=%2Faccount')
        || response.url.endsWith('/login?next=%2Faccount%2Faccess')
      )
      && text.includes('Open Chummer')
      && text.includes('Email first. Google if you prefer.')
      && text.includes('Continue with email')
      && text.includes('Continue with Google')
      && !text.includes('Account ID')
  },
  {
    url: `${baseUrl}/contact`,
    assert: text =>
      (text.includes('Discord for normal questions. Private form when needed.')
        || text.includes('Discord first. Private form if needed.'))
      && text.includes('Discord')
      && text.includes('Private form for account or crash details')
      && text.includes('Open private form')
      && text.includes('Discord or private')
      && text.includes('Send support request')
  },
  {
    url: `${baseUrl}/account/billing`,
    assert: text => isGuestBillingSurface(text)
  },
  {
    url: `${baseUrl}/participate`,
    assert: text =>
      text.includes('What should Chummer do next?')
      && text.includes('Public requests, clear bugs, useful ideas.')
      && text.includes('Current requests')
      && text.includes('Board is live.')
      && text.includes('data-chummer-participate-frame')
      && !text.includes('data-chummer-board-skin')
      && !text.includes('ProductLift')
      && !text.includes('Something went wrong')
      && !text.includes('Could not load posts')
  },
  {
    url: `${baseUrl}/roadmap`,
    assert: text =>
      text.includes('Roadmap')
      && text.includes('In progress.')
      && text.includes('Planned work lives here. Shipped work moves to Changelog.')
      && (text.includes('Work opens below.') || text.includes('Requests stay in Participate.'))
      && (text.includes('data-chummer-roadmap-frame') || text.includes('Requests stay in Participate.'))
      && !text.includes('ProductLift')
  },
  {
    url: `${baseUrl}/roadmap/board`,
    assert: (text, response) =>
      /\/roadmap\/?$/.test(response.url)
      && text.includes('In progress.')
      && text.includes('Planned work lives here. Shipped work moves to Changelog.')
      && (text.includes('Work opens below.') || text.includes('Requests stay in Participate.'))
      && !text.includes('ProductLift')
  },
  {
    url: `${baseUrl}/partizipate`,
    assert: (text, response) =>
      /\/participate\/?$/.test(response.url)
      && text.includes('What should Chummer do next?')
      && text.includes('Public requests, clear bugs, useful ideas.')
      && !text.includes('data-chummer-board-skin')
      && !text.includes('cdn.productlift.dev')
      && !text.includes('media.productlift.dev')
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
      (
        response.url.endsWith('/login?next=%2Faccount')
        || response.url.endsWith('/login?next=%2Faccount%2Faccess')
      )
      && text.includes('Open Chummer')
      && text.includes('Continue with email')
      && text.includes('Continue with Google')
      && !text.includes('Support Chummer')
  },
  {
    url: `${baseUrl}/hub/`,
    assert: (text, response) =>
      (
        response.url.endsWith('/login?next=%2Faccount')
        || response.url.endsWith('/login?next=%2Faccount%2Faccess')
      )
      && text.includes('Open Chummer')
      && text.includes('Continue with email')
      && text.includes('Continue with Google')
      && !text.includes('Support Chummer')
  },
  {
    url: `${baseUrl}/blazor/`,
    label: requireBlazor ? 'blazor' : 'delegated-blazor',
    required: requireBlazor,
    assert: (text, response) =>
      /\/blazor\/?$/.test(response.url)
      && (requireBlazor ? isBlazorReady(text) : (isBlazorReady(text) || isBlazorFallback(text)))
  },
  {
    url: `${baseUrl}/avalonia/`,
    assert: (text, response) =>
      /\/downloads\/?$/.test(response.url)
      && text.includes('Downloads')
      && text.includes('Stable')
      && text.includes('Main build for this browser')
      && text.includes('Build from source')
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
      && text.includes('Status')
      && text.includes('Updated')
      && text.includes('Downloads')
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
