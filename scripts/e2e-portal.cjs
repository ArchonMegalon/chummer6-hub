#!/usr/bin/env node
'use strict';

const { chromium } = require('playwright');

const baseUrl = (process.env.CHUMMER_PORTAL_BASE_URL || 'http://127.0.0.1:8091').replace(/\/$/, '');
const publicHost = (process.env.CHUMMER_PORTAL_PUBLIC_HOST || '').trim();
const forwardedProto = (process.env.CHUMMER_PORTAL_FORWARDED_PROTO || '').trim();
const requireBlazor = /^(1|true|yes|on)$/i.test((process.env.CHUMMER_PORTAL_REQUIRE_BLAZOR || '').trim());
const retryAttempts = Math.max(1, Number.parseInt(process.env.CHUMMER_PORTAL_RETRY_ATTEMPTS || '3', 10) || 3);
const retryDelayMs = Math.max(0, Number.parseInt(process.env.CHUMMER_PORTAL_RETRY_DELAY_MS || '500', 10) || 0);
const defaultHeaders = {};
const transientHttpStatuses = new Set([408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524]);

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

const landingRequirements = [
  ['product name', text => text.includes('Chummer')],
  ['Open Chummer action', text => text.includes('Open Chummer')],
  ['minimal Open Chummer marker', text => text.includes('minimal-open-chummer')],
  ['Build action', text => text.includes('Build')],
  ['Play action', text => text.includes('Play')],
  ['signed-out explanation', text => text.includes('Sign in first')],
  ['direct Build action', text => text.includes('site-open-chummer-menu__button" href="/build"')],
  ['direct Play action', text => text.includes('site-open-chummer-menu__button" href="/mobile/player"')],
  ['retired disabled action class must stay absent', text => !text.includes('site-open-chummer-menu__button--disabled')],
  ['retired Build target binding must stay absent', text => !text.includes('data-disabled-target="/build"')],
  ['retired Build sign-in binding must stay absent', text => !text.includes('data-sign-in-href="/login?next=%2Fbuild"')],
  ['retired Play target binding must stay absent', text => !text.includes('data-disabled-target="/mobile/player"')],
  ['retired Play sign-in binding must stay absent', text => !text.includes('data-sign-in-href="/login?next=%2Fmobile%2Fplayer"')],
  [
    'current public installer summary',
    text =>
      text.includes('Current public installer:')
      || text.includes('Current public installers:')
      || text.includes('No public installer right now.'),
  ],
  ['current public lane summary', text => text.includes('Current public lane:')],
  ['promo video link', text => hasPromoVideoLink(text)],
  ['account access sign-in link', text => text.includes('/login?next=%2Faccount%2Faccess')],
  ...requiredLandingLinks.map(link => [`landing link ${link}`, text => text.includes(link)]),
];

function landingRequirementFailures(text) {
  return landingRequirements
    .filter(([, requirement]) => !requirement(text))
    .map(([label]) => label);
}

function isTransientFailure(status, error) {
  if (typeof status === 'number') {
    return transientHttpStatuses.has(status);
  }
  if (status && status !== 'no-response') {
    return false;
  }

  const message = error instanceof Error ? error.message : String(error || '');
  return [
    'fetch failed',
    'ECONNRESET',
    'ETIMEDOUT',
    'net::ERR_',
    'Navigation timeout',
    'Timeout',
  ].some(needle => message.includes(needle));
}

async function waitBeforeRetry(attempt) {
  if (retryDelayMs > 0) {
    await new Promise(resolve => setTimeout(resolve, retryDelayMs * attempt));
  }
}

async function fetchCheckWithRetry(check) {
  let lastError = null;

  for (let attempt = 1; attempt <= retryAttempts; attempt += 1) {
    try {
      const response = await fetch(check.url, {
        method: check.method ?? 'GET',
        headers: {
          ...defaultHeaders,
          ...(check.headers ?? {})
        },
        body: check.body
      });
      const body = await response.text();
      if (response.ok || !isTransientFailure(response.status) || attempt === retryAttempts) {
        return { response, body };
      }

      console.warn(`transient-retry: ${check.url} -> HTTP ${response.status} (${attempt}/${retryAttempts})`);
    } catch (error) {
      lastError = error;
      if (!isTransientFailure(undefined, error) || attempt === retryAttempts) {
        const message = error instanceof Error ? error.message : String(error);
        throw new Error(`Portal check failed: ${check.url} -> ${message}`);
      }

      console.warn(`transient-retry: ${check.url} -> ${error.message} (${attempt}/${retryAttempts})`);
    }

    await waitBeforeRetry(attempt);
  }

  throw lastError || new Error(`Portal check failed: ${check.url} -> retry budget exhausted`);
}

function hasPromoVideoLink(text) {
  return text.includes('/media/promo/every-wonder-horizon-promo.mp4')
    && (
      text.includes('Watch 90 sec')
      || text.includes('Watch promo')
      || text.includes('Product reel')
    );
}

const currentDownloadShelfRequirements = [
  ['Downloads heading', text => text.includes('Downloads')],
  [
    'current public release summary',
    text =>
      text.includes('Current public installer')
      || text.includes('Stable release')
      || text.includes('Current public build'),
  ],
  ['Nightly lane', text => text.includes('Nightly')],
  ['version label', text => text.includes('Version ')],
  ['source-build option', text => text.includes('Build from source')],
  ['download-script label', text => text.includes('Download script')],
  ['Linux source-build script link', text => text.includes('build-chummer6-linux.sh')],
];

function currentDownloadShelfFailures(text) {
  return currentDownloadShelfRequirements
    .filter(([, requirement]) => !requirement(text))
    .map(([label]) => label);
}

function hasCurrentDownloadShelf(text) {
  return currentDownloadShelfFailures(text).length === 0;
}

function hasBlazorBaseHref(html) {
  return /<base href="[^"]*\/blazor\/"/i.test(html);
}

function isBlazorReady(text) {
  return (
    hasBlazorBaseHref(text)
    && (
      text.includes('Chummer Online')
      || (
        text.includes('Published browser surface')
        && text.includes('Published browser client')
      )
      || (
        text.includes('Launch browser workbench')
        && text.includes('Explore Chummer App')
      )
      || (
        text.includes('Character Roster')
        && text.includes('New runner')
        && text.includes('Import')
      )
      || (
        text.includes('Chummer Online')
        && text.includes('Character Roster')
        && text.includes('New runner')
        && text.includes('Import')
      )
    )
  );
}

function isBlazorRootRouteReady(response) {
  const resolvedUrl = response?.url || '';
  return (
    /\/blazor\/?$/.test(resolvedUrl)
    || (
      resolvedUrl.includes('/blazor/app')
      && resolvedUrl.includes('command=character_roster')
    )
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
    text.includes('Supporter')
    && text.includes('After this step, Chummer returns to billing.')
    && (
      (
        text.includes('Email first. Billing stays attached after this step.')
        && text.includes('Continue with email')
        && text.includes('Continue with Google')
      )
      || (
        text.includes('Google first. Billing stays attached after that step.')
        && text.includes('Continue with Google')
        && !text.includes('Continue with email')
      )
    )
    && !text.includes('Supporter is not open right now.')
    && !text.includes('Account settings')
  );
}

function isGuestAccountAccessSurface(text) {
  return (
    text.includes('Open Chummer')
    && !text.includes('Account ID')
    && (
      (
        text.includes('Email first. Google if you prefer.')
        && text.includes('Continue with email')
        && text.includes('Continue with Google')
      )
      || (
        text.includes('Email sign-in is unavailable on this host right now. Continue with Google instead.')
        && text.includes('Continue with Google')
        && !text.includes('Continue with email')
      )
    )
  );
}

function hasStatusDecisionSurface(text) {
  return (
    text.includes('Now')
    && (
      text.includes('Preview downloads')
      || text.includes('Stable downloads')
      || text.includes('Downloads paused')
    )
    && text.includes('Downloads')
    && text.includes('Version ')
    && text.includes('Help')
    && !text.includes('Nightly')
    && !text.includes('Build from source')
    && !text.includes('Checks passed')
    && !text.includes('Released')
    && !text.includes('Build run-')
  );
}

function releaseManifestFailures(text) {
  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    return [`invalid JSON: ${error.message}`];
  }

  const failures = [];
  if (typeof payload?.version !== 'string' || !payload.version.trim()) {
    failures.push('version must be a non-empty string');
  }
  if (typeof payload?.channel !== 'string' || !payload.channel.trim()) {
    failures.push('channel must be a non-empty string');
  }
  if (payload?.status !== 'published') {
    failures.push('status must be published');
  }
  if (!Array.isArray(payload?.downloads)) {
    failures.push('downloads must be an array');
    return failures;
  }

  if (payload.downloads.length === 0) {
    const tupleCoverage = payload.desktopTupleCoverage;
    const missingCoverage = [
      ...(Array.isArray(tupleCoverage?.missingRequiredPlatforms) ? tupleCoverage.missingRequiredPlatforms : []),
      ...(Array.isArray(tupleCoverage?.missingRequiredPlatformHeadPairs) ? tupleCoverage.missingRequiredPlatformHeadPairs : []),
      ...(Array.isArray(tupleCoverage?.missingRequiredPlatformHeadRidTuples) ? tupleCoverage.missingRequiredPlatformHeadRidTuples : []),
    ];
    const externalProofRequests = Array.isArray(tupleCoverage?.externalProofRequests)
      ? tupleCoverage.externalProofRequests
      : [];
    if (
      payload.rolloutState !== 'coverage_incomplete'
      || payload.supportabilityState !== 'review_required'
      || (missingCoverage.length === 0 && externalProofRequests.length === 0)
    ) {
      failures.push(
        'an empty public download projection requires coverage_incomplete/review_required posture and an explicit desktop coverage gap',
      );
    }
  }

  return failures;
}

const checks = [
  {
    url: `${baseUrl}/`,
    assert: text => landingRequirementFailures(text).length === 0,
    diagnose: text => `missing landing requirements: ${landingRequirementFailures(text).join(', ')}`
  },
  {
    url: `${baseUrl}/downloads/`,
    assert: text => hasCurrentDownloadShelf(text),
    diagnose: text => `download shelf requirements failed: ${currentDownloadShelfFailures(text).join(', ')}`
  },
  {
    url: `${baseUrl}/help`,
    assert: text =>
      text.includes('How can we help?')
      && text.includes('Pick the next step.')
      && text.includes('Install or update')
      && text.includes('Account recovery')
      && text.includes('Contact')
      && text.includes('Read the FAQ')
  },
  {
    url: `${baseUrl}/status`,
    assert: (text, response) =>
      /\/status\/?$/.test(response.url)
      && hasStatusDecisionSurface(text)
  },
  {
    url: `${baseUrl}/downloads/releases.json`,
    assert: text => releaseManifestFailures(text).length === 0,
    diagnose: text => `release manifest requirements failed: ${releaseManifestFailures(text).join(', ')}`
  },
  {
    url: `${baseUrl}/account`,
    assert: (text, response) =>
      (
        response.url.endsWith('/login?next=%2Faccount')
        || response.url.endsWith('/login?next=%2Faccount%2Faccess')
      )
      && isGuestAccountAccessSurface(text)
  },
  {
    url: `${baseUrl}/contact`,
    assert: text =>
      text.includes('Use the Chummer5 Discord server.')
      && text.includes('Normal questions and feedback belong in the Chummer5 server.')
      && text.includes('Chummer5 Discord')
      && text.includes('Open Discord')
      && !text.includes('Open private form')
      && !text.includes('Send support request')
  },
  {
    url: `${baseUrl}/account/billing`,
    assert: text => isGuestBillingSurface(text)
  },
  {
    url: `${baseUrl}/participate`,
    rendered: true,
    assert: text =>
      text.includes('Participate')
      && (text.includes('data-chummer-participate-frame') || text.includes('Board offline right now'))
      && !text.includes('Public requests, clear bugs, useful ideas.')
      && !text.includes('data-chummer-board-skin')
      && !text.includes('ProductLift')
      && !text.includes('Something went wrong')
      && !text.includes('Could not load posts')
  },
  {
    url: `${baseUrl}/participate/board?embed=1`,
    assert: (text, response) =>
      /\/participate\/board\/?\?embed=1$/.test(response.url)
      && text.includes('<base href="/participate/board/"')
      && text.includes('Chummer.run')
      && !text.includes('productlift.dev')
      && !text.includes('support@productlift.dev')
  },
  {
    url: `${baseUrl}/roadmap`,
    assert: text =>
      text.includes('Roadmap')
      && text.includes('Planned work and current requests.')
      && text.includes('data-chummer-roadmap-frame')
      && !text.includes('ProductLift')
  },
  {
    url: `${baseUrl}/roadmap/board`,
    assert: (text, response) =>
      /\/participate\/?$/.test(response.url)
      && text.includes('Participate')
      && (text.includes('data-chummer-participate-frame') || text.includes('Board offline right now'))
      && !text.includes('Public requests, clear bugs, useful ideas.')
      && !text.includes('ProductLift')
  },
  {
    url: `${baseUrl}/partizipate`,
    rendered: true,
    assert: (text, response) =>
      /\/participate\/?$/.test(response.url)
      && text.includes('Participate')
      && (text.includes('data-chummer-participate-frame') || text.includes('Board offline right now'))
      && !text.includes('Public requests, clear bugs, useful ideas.')
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
      && isGuestAccountAccessSurface(text)
      && !text.includes('Support Chummer')
  },
  {
    url: `${baseUrl}/hub/`,
    assert: (text, response) =>
      (
        response.url.endsWith('/login?next=%2Faccount')
        || response.url.endsWith('/login?next=%2Faccount%2Faccess')
      )
      && isGuestAccountAccessSurface(text)
      && !text.includes('Support Chummer')
  },
  {
    url: `${baseUrl}/blazor/`,
    label: requireBlazor ? 'blazor' : 'delegated-blazor',
    required: requireBlazor,
    assert: (text, response) =>
      isBlazorRootRouteReady(response)
      && (requireBlazor ? isBlazorReady(text) : (isBlazorReady(text) || isBlazorFallback(text)))
  },
  {
    url: `${baseUrl}/blazor/app?command=new_character`,
    label: requireBlazor ? 'blazor-new-runner-menu' : 'delegated-blazor-new-runner-menu',
    required: requireBlazor,
    rendered: true,
    run: runBlazorNewRunnerMenuCheck
  },
  {
    url: `${baseUrl}/avalonia/`,
    assert: (text, response) =>
      /\/downloads\/?$/.test(response.url)
      && hasCurrentDownloadShelf(text),
    diagnose: (text, response) => {
      const failures = currentDownloadShelfFailures(text);
      if (!/\/downloads\/?$/.test(response.url)) {
        failures.unshift(`redirect ended at ${response.url}`);
      }
      return `download shelf requirements failed: ${failures.join(', ')}`;
    }
  },
  {
    url: `${baseUrl}/session/`,
    assert: (text, response) =>
      /\/mobile\/player\/?$/.test(response.url)
      && text.includes('data-play-surface="install-only"')
      && text.includes('data-install-role="player"')
  },
  {
    url: `${baseUrl}/coach/`,
    assert: (text, response) =>
      /\/status\/?$/.test(response.url)
      && hasStatusDecisionSurface(text)
  }
];

async function runRenderedCheck(browser, check) {
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    extraHTTPHeaders: defaultHeaders,
  });
  const page = await context.newPage();
  try {
    if (typeof check.run === 'function') {
      return await check.run(page, check);
    }

    const response = await page.goto(check.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    if (!response || !response.ok()) {
      return {
        ok: false,
        status: response ? response.status() : 'no-response',
        text: '',
        response: { url: page.url() },
      };
    }

    await waitForPageCondition(
      page,
      () => {
        const text = (document.body && document.body.innerText) || '';
        return /Participate|Board offline right now/i.test(text);
      },
      15000,
      'participate surface did not reach a rendered ready or offline state',
    );

    const bodyText = (await page.locator('body').innerText()).replace(/\s+/g, ' ').trim();
    const hasParticipateFrame = await page.locator('iframe[data-chummer-participate-frame]').count() > 0;

    return {
      ok: true,
      status: response.status(),
      text: `${bodyText}${hasParticipateFrame ? ' data-chummer-participate-frame' : ''}`.trim(),
      response: { url: page.url() },
    };
  } finally {
    await context.close();
  }
}

async function waitForPageCondition(page, condition, timeoutMs, failureLabel) {
  try {
    await page.waitForFunction(condition, undefined, { timeout: timeoutMs });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`${failureLabel}: ${detail}`);
  }
}

async function runRenderedCheckWithRetry(browser, check) {
  let rendered = null;

  for (let attempt = 1; attempt <= retryAttempts; attempt += 1) {
    try {
      rendered = await runRenderedCheck(browser, check);
    } catch (error) {
      rendered = {
        ok: false,
        status: 'no-response',
        text: '',
        response: { url: check.url },
        error: error instanceof Error ? error.message : String(error),
      };
    }

    if (rendered.ok || !isTransientFailure(rendered.status, rendered.error) || attempt === retryAttempts) {
      return rendered;
    }

    console.warn(`transient-retry: ${check.url} -> ${rendered.error || `HTTP ${rendered.status}`} (${attempt}/${retryAttempts})`);
    await waitBeforeRetry(attempt);
  }

  return rendered;
}

async function runBlazorNewRunnerMenuCheck(page, check) {
  const response = await page.goto(check.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (!response || !response.ok()) {
    return {
      ok: false,
      status: response ? response.status() : 'no-response',
      text: '',
      response: { url: page.url() },
    };
  }

  try {
    await page.waitForSelector('#dialogBackdrop[data-dialog-id="dialog.new_character"]', { timeout: 60000 });

    const buildMethod = page.locator('label[data-field-id="newCharacterBuildMethod"] select');
    await buildMethod.waitFor({ state: 'visible', timeout: 30000 });
    await buildMethod.selectOption('Karma');
    const buildMethodValue = await buildMethod.inputValue();
    if (buildMethodValue !== 'Karma') {
      throw new Error(`Expected Build Method to switch to Karma before closing the startup dialog, got '${buildMethodValue}'.`);
    }

    const fileMenu = page.locator('button.menu-btn.classic-menu-button').filter({ hasText: 'File' }).first();
    await fileMenu.waitFor({ state: 'visible', timeout: 15000 });
    const fileMenuLockedDuringDialog = await fileMenu.isDisabled();
    if (!fileMenuLockedDuringDialog) {
      throw new Error('Expected File menu to stay disabled while the startup dialog is open.');
    }

    const newTool = page.locator('button.tool-btn.classic-tool-button').filter({ hasText: 'New' }).first();
    const newToolLockedDuringDialog = await newTool.isDisabled();
    if (!newToolLockedDuringDialog) {
      throw new Error('Expected New tool button to stay disabled while the startup dialog is open.');
    }

    await page.locator('#dialogClose').click({ timeout: 15000 });
    await page.waitForSelector('#dialogBackdrop[data-dialog-id="dialog.new_character"]', { state: 'detached', timeout: 15000 });

    await fileMenu.waitFor({ state: 'visible', timeout: 15000 });
    const fileMenuEnabledAfterClose = await fileMenu.isEnabled();
    if (!fileMenuEnabledAfterClose) {
      throw new Error('Expected File menu to become enabled after closing the startup dialog.');
    }

    const newToolEnabledAfterClose = await newTool.isEnabled();
    if (!newToolEnabledAfterClose) {
      throw new Error('Expected New tool button to become enabled after closing the startup dialog.');
    }

    await fileMenu.click({ timeout: 15000 });
    await waitForPageCondition(
      page,
      () => {
        const button = Array.from(document.querySelectorAll('button.menu-btn.classic-menu-button'))
          .find(element => element.textContent?.includes('File'));
        if (!button) {
          return false;
        }

        const ariaExpanded = button.getAttribute('aria-expanded') || '';
        const classes = (button.getAttribute('class') || '').split(/\s+/);
        return ariaExpanded === 'true' || classes.includes('active');
      },
      15000,
      'File menu did not expose its expanded state after click',
    );
    const fileMenuExpandedState = await fileMenu.evaluate((element) => ({
      ariaExpanded: element.getAttribute('aria-expanded') || '',
      className: element.getAttribute('class') || ''
    }));
    const fileMenuExpanded = fileMenuExpandedState.ariaExpanded === 'true'
      || fileMenuExpandedState.className.split(/\s+/).includes('active');
    if (!fileMenuExpanded) {
      throw new Error(
        `Expected File menu to expand while the startup dialog is open, got `
        + `aria-expanded='${fileMenuExpandedState.ariaExpanded}' class='${fileMenuExpandedState.className}'.`);
    }

    const newRunner = page.locator('button.menu-item.classic-menu-item').filter({ hasText: 'New runner' }).first();
    await newRunner.waitFor({ state: 'visible', timeout: 15000 });
    await newRunner.click({ timeout: 15000 });

    await page.waitForSelector('#dialogBackdrop[data-dialog-id="dialog.new_character"]', { state: 'visible', timeout: 15000 });
    await waitForPageCondition(
      page,
      () => document.querySelector('label[data-field-id="newCharacterBuildMethod"] select')?.value === 'Priority',
      15000,
      'new-character dialog did not reset Build Method to Priority after File → New runner',
    );
    const buildMethodReset = await buildMethod.inputValue();
    if (buildMethodReset !== 'Priority') {
      throw new Error(`Expected File -> New runner to reopen the startup dialog with Priority selected, got '${buildMethodReset}'.`);
    }

    const dialogVisible = await page.locator('#dialogBackdrop[data-dialog-id="dialog.new_character"]').isVisible();
    if (!dialogVisible) {
      throw new Error('Expected the new character startup dialog backdrop to remain visible after selecting File -> New runner.');
    }

    const fileMenuLockedAfterReopen = await fileMenu.isDisabled();
    if (!fileMenuLockedAfterReopen) {
      throw new Error('Expected File menu to return to the disabled state after reopening the startup dialog.');
    }

    await waitForPageCondition(
      page,
      () => {
        const button = Array.from(document.querySelectorAll('button.menu-btn.classic-menu-button'))
          .find(element => element.textContent?.includes('File'));
        if (!button) {
          return false;
        }

        const ariaExpanded = button.getAttribute('aria-expanded') || '';
        const classes = (button.getAttribute('class') || '').split(/\s+/);
        return ariaExpanded === 'false' || !classes.includes('active');
      },
      15000,
      'File menu did not collapse after selecting New runner',
    );
    const fileMenuCollapsedState = await fileMenu.evaluate((element) => ({
      ariaExpanded: element.getAttribute('aria-expanded') || '',
      className: element.getAttribute('class') || ''
    }));
    const fileMenuCollapsed = fileMenuCollapsedState.ariaExpanded === 'false'
      || !fileMenuCollapsedState.className.split(/\s+/).includes('active');
    if (!fileMenuCollapsed) {
      throw new Error(
        `Expected File menu to collapse after selecting New runner, got `
        + `aria-expanded='${fileMenuCollapsedState.ariaExpanded}' class='${fileMenuCollapsedState.className}'.`);
    }

    return {
      ok: true,
      status: response.status(),
      text: `dialog=${dialogVisible} buildMethod=${buildMethodReset} fileMenuLockedDuringDialog=${fileMenuLockedDuringDialog} fileMenuEnabledAfterClose=${fileMenuEnabledAfterClose} fileMenuCollapsed=${fileMenuCollapsed}`,
      response: { url: page.url() },
    };
  } catch (error) {
    return {
      ok: false,
      status: response.status(),
      text: '',
      response: { url: page.url() },
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

(async () => {
  const delegatedWarnings = [];
  let browser = null;

  try {
    for (const check of checks) {
      let body;
      let response;
      if (check.rendered) {
        if (!browser) {
          browser = await chromium.launch({
            channel: process.env.CHUMMER_PLAYWRIGHT_CHANNEL?.trim() || 'chromium',
            headless: true,
            args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-quic'],
          });
        }

        const rendered = await runRenderedCheckWithRetry(browser, check);
        body = rendered.text;
        response = rendered.response;
        if (!rendered.ok) {
          const renderedFailure = rendered.error || `HTTP ${rendered.status}`;
          if (check.required === false) {
            const message = `delegated-not-ready: ${check.label ?? check.url} -> ${renderedFailure}`;
            delegatedWarnings.push(message);
            console.warn(message);
            continue;
          }

          throw new Error(`Portal check failed: ${check.url} -> ${renderedFailure}`);
        }
      } else {
        const fetched = await fetchCheckWithRetry(check);
        response = fetched.response;
        body = fetched.body;
        if (!response.ok) {
          if (check.required === false) {
            const message = `delegated-not-ready: ${check.label ?? check.url} -> HTTP ${response.status}`;
            delegatedWarnings.push(message);
            console.warn(message);
            continue;
          }

          throw new Error(`Portal check failed: ${check.url} -> HTTP ${response.status}`);
        }
      }

      let passed = false;
      try {
        passed = typeof check.assert === 'function'
          ? Boolean(check.assert(body, response))
          : true;
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
        const diagnostic = typeof check.diagnose === 'function'
          ? String(check.diagnose(body, response) || '').trim()
          : '';
        const failureDetail = diagnostic ? `: ${diagnostic}` : '';
        if (check.required === false) {
          const message = `delegated-not-ready: ${check.label ?? check.url} -> assertion returned false${failureDetail}`;
          delegatedWarnings.push(message);
          console.warn(message);
          continue;
        }

        throw new Error(`Portal check failed: ${check.url} -> assertion returned false${failureDetail}`);
      }

      console.log(`ok: ${check.url}`);
    }

    if (delegatedWarnings.length > 0) {
      console.warn(`portal E2E completed with delegated warnings: ${delegatedWarnings.length}`);
    }

    console.log('portal E2E completed');
  } finally {
    if (browser) {
      await browser.close();
    }
  }
})().catch(error => {
  console.error(error.message);
  process.exit(1);
});
