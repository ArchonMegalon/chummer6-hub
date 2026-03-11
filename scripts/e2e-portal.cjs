#!/usr/bin/env node
'use strict';

const requiredLandingLinks = [
  '/blazor/',
  '/hub/',
  '/session/',
  '/coach/',
  '/avalonia/',
  '/downloads/',
  '/docs/',
  '/api/health'
];

const checks = [
  {
    url: 'http://chummer-portal:8080/',
    assert: text =>
      text.includes('Chummer Portal') &&
      requiredLandingLinks.every(link => text.includes(link))
  },
  {
    url: 'http://chummer-portal:8080/blazor/health',
    assert: text => {
      const payload = JSON.parse(text);
      return payload?.pathBase === '/blazor' && payload?.ok === true;
    }
  },
  {
    url: 'http://chummer-portal:8080/blazor/',
    assert: text => /<base href="[^"]*\/blazor\/"/i.test(text)
  },
  {
    url: 'http://chummer-portal:8080/blazor/deep-link-check',
    assert: text => /<base href="[^"]*\/blazor\/"/i.test(text)
  },
  {
    url: 'http://chummer-portal:8080/hub/health',
    assert: text => {
      const payload = JSON.parse(text);
      return payload?.head === 'hub-web' && payload?.pathBase === '/hub' && payload?.ok === true;
    }
  },
  {
    url: 'http://chummer-portal:8080/hub/',
    assert: text => /<base href="[^"]*\/hub\/"/i.test(text) && text.includes('ChummerHub Web')
  },
  {
    url: 'http://chummer-portal:8080/session/health',
    assert: text => {
      const payload = JSON.parse(text);
      return payload?.head === 'session-web' && payload?.pathBase === '/session' && payload?.ok === true;
    }
  },
  {
    url: 'http://chummer-portal:8080/session/',
    assert: text => /<base href="[^"]*\/session\/"/i.test(text) && text.includes('Chummer Session Web')
  },
  {
    url: 'http://chummer-portal:8080/coach/health',
    assert: text => {
      const payload = JSON.parse(text);
      return payload?.head === 'coach-web' && payload?.pathBase === '/coach' && payload?.ok === true;
    }
  },
  {
    url: 'http://chummer-portal:8080/coach/',
    assert: text => /<base href="[^"]*\/coach\/"/i.test(text) && text.includes('Chummer Coach')
  },
  {
    url: 'http://chummer-portal:8080/avalonia/',
    assert: text => text.includes('Avalonia Browser Host')
  },
  {
    url: 'http://chummer-portal:8080/avalonia/health',
    assert: text => {
      const payload = JSON.parse(text);
      return payload?.head === 'avalonia-browser' && payload?.pathBase === '/avalonia' && payload?.ok === true;
    }
  },
  {
    method: 'POST',
    url: 'http://chummer-portal:8080/blazor/_blazor/negotiate?negotiateVersion=1',
    headers: {
      'Content-Type': 'text/plain;charset=UTF-8'
    },
    body: '',
    assert: text => {
      const payload = JSON.parse(text);
      return typeof payload?.connectionId === 'string' && payload.connectionId.length > 0;
    }
  },
  {
    url: 'http://chummer-portal:8080/api/health',
    assert: text => {
      const payload = JSON.parse(text);
      return payload?.ok === true;
    }
  },
  {
    url: 'http://chummer-portal:8080/api/tools/master-index',
    assert: text => !text.includes('missing_or_invalid_api_key')
  },
  {
    url: 'http://chummer-portal:8080/api/ai/status',
    assert: text => {
      const payload = JSON.parse(text);
      return payload?.status === 'scaffolded'
        && Array.isArray(payload?.routes)
        && payload.routes.includes('coach')
        && Array.isArray(payload?.providers)
        && !text.includes('missing_or_invalid_api_key');
    }
  },
  {
    url: 'http://chummer-portal:8080/openapi/v1.json',
    assert: text => {
      const payload = JSON.parse(text);
      return typeof payload?.openapi === 'string' && payload.openapi.length > 0;
    }
  },
  {
    url: 'http://chummer-portal:8080/docs/',
    assert: text =>
      text.includes('Self-hosted OpenAPI explorer') &&
      text.includes('/docs/docs.js') &&
      !text.toLowerCase().includes('jsdelivr')
  },
  {
    url: 'http://chummer-portal:8080/downloads/releases.json',
    assert: text => {
      const payload = JSON.parse(text);
      return typeof payload?.version === 'string'
        && typeof payload?.status === 'string'
        && typeof payload?.source === 'string'
        && Array.isArray(payload?.downloads);
    }
  },
  {
    url: 'http://chummer-portal:8080/downloads/',
    assert: text =>
      text.includes('Desktop Downloads') &&
      text.includes('/downloads/releases.json') &&
      text.includes('No published desktop builds yet') &&
      text.includes('fallback-link')
  }
];

(async () => {
  for (const check of checks) {
    const response = await fetch(check.url, {
      method: check.method ?? 'GET',
      headers: check.headers,
      body: check.body
    });
    const body = await response.text();
    if (!response.ok) {
      throw new Error(`Portal check failed: ${check.url} -> HTTP ${response.status}`);
    }

    let passed = false;
    try {
      passed = Boolean(check.assert(body));
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
