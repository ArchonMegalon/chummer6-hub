import { expect, test } from 'playwright/test';
import {
  candidateBindingReceipt,
  loadUiFrameCandidateBinding,
  verifyUiFrameCandidateAuthority,
  verifyUiFrameCandidateHeaders,
  writeUiFrameCandidateJson,
  writeUiFrameCandidateReport,
  type UiFrameAuthorityObservation,
  type UiFrameCandidateBinding,
} from './ui-frame-candidate-binding';

const baseUrl = process.env.BASE_URL?.trim()
  || process.env.CHUMMER_PUBLIC_BASE_URL?.trim()
  || 'https://chummer.run';
const frameIntegrityTimeoutMs = Number.parseInt(process.env.CHUMMER_UI_FRAME_TEST_TIMEOUT_MS || '', 10);
const frameIntegrityTestTimeout = Number.isFinite(frameIntegrityTimeoutMs) && frameIntegrityTimeoutMs > 0
  ? frameIntegrityTimeoutMs
  : 600000;

const viewports = [
  { name: 'phone-390', width: 390, height: 844 },
  { name: 'phone-412', width: 412, height: 915 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop-1366', width: 1366, height: 768 },
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'wide', width: 1920, height: 1080 },
];

type ViewportName = (typeof viewports)[number]['name'];

const allViewportNames: ViewportName[] = viewports.map((viewport) => viewport.name);
const compactViewportNames: ViewportName[] = ['phone-390', 'tablet', 'desktop-1366'];

const routeViewportMatrix: Array<{ route: string; viewportNames: ViewportName[] }> = [
  { route: '/', viewportNames: allViewportNames },
  { route: '/downloads', viewportNames: allViewportNames },
  { route: '/ledger/map', viewportNames: allViewportNames },
  { route: '/login?next=%2Faccount%2Faccess', viewportNames: allViewportNames },
  { route: '/status', viewportNames: compactViewportNames },
  { route: '/faq', viewportNames: compactViewportNames },
  { route: '/packages', viewportNames: compactViewportNames },
  { route: '/mobile', viewportNames: compactViewportNames },
  { route: '/mobile/player', viewportNames: compactViewportNames },
  { route: '/mobile/gm', viewportNames: compactViewportNames },
  { route: '/mobile/observer', viewportNames: compactViewportNames },
  { route: '/play', viewportNames: compactViewportNames },
  { route: '/play/continuity', viewportNames: compactViewportNames },
  { route: '/feedback', viewportNames: compactViewportNames },
  { route: '/docs/embed/origin-dossier-the-name-she-chose', viewportNames: compactViewportNames },
  {
    route: '/account/access/install-link?installationId=ins-ui-gate&headId=avalonia&applicationVersion=run-20260612-121055&releaseChannel=docker&platform=windows&arch=x64&installLinkMode=browser_callback&installLinkTransport=grant_callback&installLinkCallbackUri=chummer%3A%2F%2Finstall-link',
    viewportNames: compactViewportNames,
  },
];

const singleLineRules: Array<{ selector: string; minWidth: number; label: string }> = [
  { selector: '.site-brand__wordmark', minWidth: 320, label: 'site-brand wordmark' },
  { selector: '.site-footer__wordmark', minWidth: 768, label: 'footer wordmark' },
  { selector: '.hero-brand', minWidth: 1024, label: 'hero brand' },
  { selector: '.minimal-hero h1', minWidth: 1280, label: 'minimal hero title' },
  { selector: '.home-hero__title', minWidth: 1280, label: 'home hero title' },
  { selector: '.site-nav a', minWidth: 1366, label: 'top navigation item' },
  { selector: '.page-title', minWidth: 1366, label: 'page title' },
  { selector: '.editorial-title', minWidth: 1366, label: 'editorial title' },
];

const transientNavigationNeedles = [
  'ERR_NETWORK_CHANGED',
  'net::ERR_',
  'chrome-error://chromewebdata',
  'interrupted by another navigation',
  'Navigation timeout',
  'Timeout',
  'chrome-error://chromewebdata/',
  'interrupted by another navigation',
];

const transientPageClosureNeedles = [
  'Target page, context or browser has been closed',
  'Target crashed',
];

function envInteger(name: string, fallback: number): number {
  const raw = process.env[name]?.trim();
  if (!raw) {
    return fallback;
  }

  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

const matrixTimeoutMs = envInteger('CHUMMER_UI_FRAME_TEST_TIMEOUT_MS', 600000);
const networkIdleSettleMs = envInteger('CHUMMER_UI_FRAME_NETWORK_IDLE_MS', 1000);

type FrameFailure = {
  route: string;
  viewport: string;
  selector: string;
  text: string;
  reason: string;
  element: Record<string, number>;
  frame?: Record<string, number>;
  frameOverflow?: string;
};

let candidateBinding: UiFrameCandidateBinding;
let authorityObservation: UiFrameAuthorityObservation;
let completedFramePayload: Record<string, unknown> | undefined;
let completedFrameReport: string | undefined;
let completedLoginPayload: Record<string, unknown> | undefined;

type NetworkViolation = {
  method: string;
  url: string;
  reason: string;
};

type PageAudit = {
  context: import('playwright/test').BrowserContext;
  violations: NetworkViolation[];
};

const pageAudits = new WeakMap<import('playwright/test').Page, PageAudit>();

async function gotoWithRetry(page: import('playwright/test').Page, route: string, attempts = 3) {
  let lastError: unknown;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForLoadState('networkidle', { timeout: networkIdleSettleMs }).catch(() => {});
      if ((response?.status() ?? 0) >= 500 && attempt < attempts) {
        await page.waitForTimeout(500 * attempt);
        continue;
      }

      return response;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      const transient = transientNavigationNeedles.some((needle) => message.includes(needle));
      if (!transient || attempt === attempts) {
        throw error;
      }

      await page.waitForTimeout(500 * attempt);
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

async function createAuditedPage(
  browser: import('playwright/test').Browser,
  viewport: { width: number; height: number },
) {
  const context = await browser.newContext({
    baseURL: candidateBinding.baseUrl,
    viewport,
    serviceWorkers: 'block',
  });
  const violations: NetworkViolation[] = [];
  const violationKeys = new Set<string>();
  const recordViolation = (violation: NetworkViolation) => {
    const key = `${violation.reason}\0${violation.method}\0${violation.url}`;
    if (!violationKeys.has(key)) {
      violationKeys.add(key);
      violations.push(violation);
    }
  };
  context.on('request', (request) => {
    const method = request.method();
    const url = request.url();
    let origin = '';
    try {
      origin = new URL(url).origin;
    } catch {
      recordViolation({ method, url, reason: 'request URL is not absolute' });
      return;
    }
    if (method !== 'GET') {
      recordViolation({ method, url, reason: 'non-GET request blocked' });
    } else if (origin !== candidateBinding.baseUrl) {
      recordViolation({ method, url, reason: 'off-origin request blocked' });
    }
  });
  await context.route('**/*', async (requestRoute) => {
    const request = requestRoute.request();
    const method = request.method();
    const url = request.url();
    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch {
      recordViolation({ method, url, reason: 'request URL is not absolute' });
      await requestRoute.abort('blockedbyclient');
      return;
    }
    if (method !== 'GET') {
      recordViolation({ method, url, reason: 'non-GET request blocked' });
      await requestRoute.abort('blockedbyclient');
      return;
    }
    if (parsed.origin !== candidateBinding.baseUrl) {
      recordViolation({ method, url, reason: 'off-origin request blocked' });
      await requestRoute.abort('blockedbyclient');
      return;
    }
    const resourceType = request.resourceType();
    if (resourceType === 'media') {
      await requestRoute.abort();
      return;
    }
    await requestRoute.continue({
      headers: {
        ...request.headers(),
        ...candidateBinding.requestHeaders,
      },
    });
  });
  await context.addInitScript(() => {
    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: false,
      value: function BlockedAuditWebSocket() {
        throw new Error('WebSocket is disabled by the read-only UI-frame audit');
      },
      writable: false,
    });
    const originalGetContext = HTMLCanvasElement.prototype.getContext as unknown as (
      this: HTMLCanvasElement,
      type: string,
      ...args: unknown[]
    ) => RenderingContext | null;
    HTMLCanvasElement.prototype.getContext = function getContext(type: string, ...args: unknown[]) {
      if (String(type).toLowerCase().includes('webgl')) {
        return null;
      }

      return originalGetContext.call(this, type, ...args);
    } as unknown as typeof HTMLCanvasElement.prototype.getContext;
  });
  const page = await context.newPage();
  pageAudits.set(page, { context, violations });

  return page;
}

function networkViolations(page: import('playwright/test').Page): NetworkViolation[] {
  return [...(pageAudits.get(page)?.violations ?? [])];
}

async function closeAuditedPage(page: import('playwright/test').Page | undefined): Promise<void> {
  if (!page) {
    return;
  }
  const audit = pageAudits.get(page);
  if (audit) {
    await audit.context.close().catch(() => {});
    pageAudits.delete(page);
    return;
  }
  await page.close().catch(() => {});
}

async function launchAuditBrowser(
  playwright: import('playwright/test').Playwright,
  browserName: string,
) {
  if (browserName === 'firefox') {
    return playwright.firefox.launch();
  }

  if (browserName === 'webkit') {
    return playwright.webkit.launch();
  }

  return playwright.chromium.launch({
    channel: process.env.CHUMMER_PLAYWRIGHT_CHANNEL?.trim() || 'chromium',
    args: ['--disable-quic'],
  });
}

async function verifyCandidateNavigationResponse(
  page: import('playwright/test').Page,
  response: import('playwright/test').Response | null,
  route: string,
): Promise<number> {
  if (!response) {
    throw new Error(`${route}: navigation returned no HTTP response`);
  }
  const status = response.status();
  if (status !== 200) {
    throw new Error(`${route}: navigation returned HTTP ${status}, expected 200`);
  }
  if (response.request().method() !== 'GET') {
    throw new Error(`${route}: navigation used ${response.request().method()}, expected read-only GET`);
  }
  const expectedUrl = new URL(route, `${candidateBinding.baseUrl}/`);
  const observedUrl = new URL(response.url());
  const finalPageUrl = new URL(page.url());
  const exactRoute = (value: URL) => value.origin === expectedUrl.origin
    && value.pathname === expectedUrl.pathname
    && value.search === expectedUrl.search;
  if (!exactRoute(observedUrl) || !exactRoute(finalPageUrl)) {
    throw new Error(
      `${route}: navigation redirected or changed exact route (response=${observedUrl.href}, page=${finalPageUrl.href})`,
    );
  }
  verifyUiFrameCandidateHeaders(await response.allHeaders(), candidateBinding, route);
  return status;
}

test.beforeAll(async ({ playwright }) => {
  candidateBinding = loadUiFrameCandidateBinding();
  if (new URL(baseUrl).origin !== candidateBinding.baseUrl) {
    throw new Error('Playwright base URL does not match the candidate binding base URL');
  }
  const request = await playwright.request.newContext({ baseURL: candidateBinding.baseUrl });
  try {
    authorityObservation = await verifyUiFrameCandidateAuthority(request, candidateBinding);
  } finally {
    await request.dispose();
  }
});

test.afterAll(() => {
  if (!completedFramePayload || !completedFrameReport || !completedLoginPayload) {
    return;
  }
  if (completedFramePayload.status !== 'pass' || completedLoginPayload.status !== 'pass') {
    return;
  }
  writeUiFrameCandidateJson(
    candidateBinding,
    'LOGIN_COMPACT_FRAME.generated.json',
    completedLoginPayload,
  );
  writeUiFrameCandidateReport(candidateBinding, completedFrameReport);
  writeUiFrameCandidateJson(
    candidateBinding,
    'UI_FRAME_INTEGRITY.generated.json',
    completedFramePayload,
  );
});

test('public UI elements are not cut off by their frames outside intentional scroll panels', async ({ playwright, browserName }) => {
  test.setTimeout(frameIntegrityTestTimeout);
  const failures: FrameFailure[] = [];
  const pageResults: Array<Record<string, unknown>> = [];
  const routeMatrixStartedAtUtc = new Date().toISOString();
  let auditBrowser = await launchAuditBrowser(playwright, browserName);
  const viewportByName = new Map(viewports.map((viewport) => [viewport.name, viewport] as const));

  try {
    for (const scenario of routeViewportMatrix) {
      for (const viewportName of scenario.viewportNames) {
        const viewport = viewportByName.get(viewportName);
        if (!viewport) {
          throw new Error(`missing viewport config for ${viewportName}`);
        }

        const route = scenario.route;
        let routeCompleted = false;
        let pageClosureRetries = 0;
        while (!routeCompleted) {
          let page: import('playwright/test').Page | undefined;
          try {
            page = await createAuditedPage(auditBrowser, { width: viewport.width, height: viewport.height });
            const response = await gotoWithRetry(page, route);

            let status: number;
            try {
              status = await verifyCandidateNavigationResponse(page, response, route);
            } catch (error) {
              const reason = error instanceof Error ? error.message : String(error);
              failures.push({
                route,
                viewport: viewport.name,
                selector: 'document',
                text: '',
                reason: `candidate identity verification failed: ${reason}`,
                element: { x: 0, y: 0, width: 0, height: 0, right: 0, bottom: 0 },
              });
              pageResults.push({
                route,
                viewport: viewport.name,
                status: response?.status() ?? 0,
                failure_count: 1,
                candidate_identity_verified: false,
              });
              routeCompleted = true;
              continue;
            }

            const routeFailures = await page.evaluate((lineRulesArg) => {
        type Rect = { x: number; y: number; width: number; height: number; right: number; bottom: number };
        type Failure = {
          selector: string;
          text: string;
          reason: string;
          element: Rect;
          frame?: Rect;
          frameOverflow?: string;
        };

        type LineFailure = {
          selector: string;
          text: string;
          reason: string;
          element: Rect;
          lines: number;
        };

        const tolerance = 1.5;
        const auditedSelector = [
          'a',
          'button',
          'input',
          'select',
          'textarea',
          '[role="button"]',
          '[role="link"]',
          '[role="tab"]',
          '[role="menuitem"]',
          '.button-like',
          '.action-pill',
          '.tag',
          '.hero-brand',
          '.hero-headline',
          '.page-title',
          '.section-title',
          '.minimal-hero h1',
          '.launch-hero__actions',
          '.stacked-actions',
          '.auth-panel',
          '.auth-benefits',
          '.home-status-card',
          '.recommended-download__card',
          '.package-card',
          '.feature-card',
          '.status-card',
          '.ledger-flagship__actions',
          '.site-brand',
          '.site-brand__wordmark',
          '.site-footer__wordmark',
          '[data-geoscape-panel]',
          '[data-geoscape-controls]',
          '[data-geoscape-signal-rail]',
          '[class*="card"]',
          '[class*="panel"]',
          '[class*="rail"]',
          '[class*="actions"]',
        ].join(',');

        function rectOf(element: Element): Rect {
          const rect = element.getBoundingClientRect();
          return {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            right: rect.right,
            bottom: rect.bottom,
          };
        }

        function clipOverflow(style: CSSStyleDeclaration): string {
          return `${style.overflowX}/${style.overflowY}`;
        }

        function clipsChildren(style: CSSStyleDeclaration): boolean {
          const values = [style.overflowX, style.overflowY];
          return values.some((value) => value === 'hidden' || value === 'clip' || value === 'auto' || value === 'scroll');
        }

        function clipsWithoutScrollPanel(style: CSSStyleDeclaration): boolean {
          const values = [style.overflowX, style.overflowY];
          return values.some((value) => value === 'hidden' || value === 'clip');
        }

        function isIntentionalScrollPanel(element: HTMLElement, style: CSSStyleDeclaration): boolean {
          const values = [style.overflowX, style.overflowY];
          const allowsScroll = values.some((value) => value === 'auto' || value === 'scroll');
          if (!allowsScroll) {
            return false;
          }

          return element.scrollHeight > element.clientHeight + tolerance
            || element.scrollWidth > element.clientWidth + tolerance;
        }

        function lineCount(element: HTMLElement): number {
          const rects = Array.from(element.getClientRects());
          return Math.max(1, rects.length);
        }

        function hasScrollableAncestorBetween(element: HTMLElement, ancestor: HTMLElement | null): boolean {
          let current = element.parentElement;
          while (current && current !== ancestor) {
            const style = getComputedStyle(current);
            if (isIntentionalScrollPanel(current, style)) {
              return true;
            }
            current = current.parentElement;
          }
          return false;
        }

        function selectorFor(element: Element): string {
          if (element.id) {
            return `#${CSS.escape(element.id)}`;
          }

          const attr = ['data-homepage-section', 'data-public-section', 'data-ledger-redesign', 'data-geoscape-panel', 'data-geoscape-controls', 'data-geoscape-signal-rail']
            .map((name) => [name, element.getAttribute(name)] as const)
            .find(([, value]) => value);
          if (attr) {
            return `[${attr[0]}="${CSS.escape(attr[1] ?? '')}"]`;
          }

          const className = typeof (element as HTMLElement).className === 'string'
            ? (element as HTMLElement).className.trim().split(/\s+/).slice(0, 3).join('.')
            : '';
          const classSelector = className ? `.${className}` : '';
          return `${element.tagName.toLowerCase()}${classSelector}`;
        }

        function textFor(element: HTMLElement): string {
          if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
            return element.value || element.placeholder || element.getAttribute('aria-label') || '';
          }

          return (element.textContent || element.getAttribute('aria-label') || '')
            .replace(/\s+/g, ' ')
            .trim()
            .slice(0, 140);
        }

        function isVisible(element: HTMLElement): boolean {
          const closedDetails = element.closest('details:not([open])');
          if (closedDetails && !element.closest('summary')) {
            return false;
          }

          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.display !== 'none'
            && style.visibility !== 'hidden'
            && Number(style.opacity || '1') > 0.01
            && rect.width > 2
            && rect.height > 2;
        }

        function hasSubstance(element: HTMLElement): boolean {
          if (element.matches('input,select,textarea,button,a,[role="button"],[role="link"],[role="tab"],[role="menuitem"]')) {
            return true;
          }

          return textFor(element).length > 0;
        }

        function isInteractiveOrControl(element: HTMLElement): boolean {
          return element.matches('input,select,textarea,button,a,[role="button"],[role="link"],[role="tab"],[role="menuitem"],.button-like,.action-pill');
        }

        const failures: Failure[] = [];
        const lineFailures: LineFailure[] = [];
        const root = document.documentElement;
        const pageOverflow = root.scrollWidth - root.clientWidth;
        if (pageOverflow > tolerance) {
          failures.push({
            selector: 'document.documentElement',
            text: '',
            reason: `page has ${Math.round(pageOverflow)}px horizontal overflow`,
            element: rectOf(root),
          });
        }

        const candidates = Array.from(document.querySelectorAll<HTMLElement>(auditedSelector))
          .filter((element) => isVisible(element) && hasSubstance(element));

        for (const element of candidates) {
          const elementRect = rectOf(element);
          const elementStyle = getComputedStyle(element);
          const elementCanClip = clipsWithoutScrollPanel(elementStyle);
          if (isInteractiveOrControl(element)
              && element.scrollWidth > element.clientWidth + tolerance
              && !isIntentionalScrollPanel(element, elementStyle)) {
            failures.push({
              selector: selectorFor(element),
              text: textFor(element),
              reason: `element content exceeds its own width by ${Math.round(element.scrollWidth - element.clientWidth)}px`,
              element: elementRect,
              frameOverflow: clipOverflow(elementStyle),
            });
          }

          if (isInteractiveOrControl(element)
              && elementCanClip
              && element.scrollHeight > element.clientHeight + tolerance
              && !isIntentionalScrollPanel(element, elementStyle)) {
            failures.push({
              selector: selectorFor(element),
              text: textFor(element),
              reason: `element content exceeds its own height by ${Math.round(element.scrollHeight - element.clientHeight)}px`,
              element: elementRect,
              frameOverflow: clipOverflow(elementStyle),
            });
          }

          let ancestor = element.parentElement;
          while (ancestor && ancestor !== document.body && ancestor !== document.documentElement) {
            const style = getComputedStyle(ancestor);
            if (!clipsChildren(style)) {
              ancestor = ancestor.parentElement;
              continue;
            }

            if (isIntentionalScrollPanel(ancestor, style) || hasScrollableAncestorBetween(element, ancestor)) {
              ancestor = ancestor.parentElement;
              continue;
            }

            if (!clipsWithoutScrollPanel(style)) {
              ancestor = ancestor.parentElement;
              continue;
            }

            const frameRect = rectOf(ancestor);
            const clippedLeft = elementRect.x < frameRect.x - tolerance;
            const clippedRight = elementRect.right > frameRect.right + tolerance;
            const clippedTop = elementRect.y < frameRect.y - tolerance;
            const clippedBottom = elementRect.bottom > frameRect.bottom + tolerance;
            if (clippedLeft || clippedRight || clippedTop || clippedBottom) {
              const sides = [
                clippedLeft ? 'left' : '',
                clippedRight ? 'right' : '',
                clippedTop ? 'top' : '',
                clippedBottom ? 'bottom' : '',
              ].filter(Boolean).join('/');
              failures.push({
                selector: selectorFor(element),
                text: textFor(element),
                reason: `cut off by ${selectorFor(ancestor)} on ${sides}`,
                element: elementRect,
                frame: frameRect,
                frameOverflow: clipOverflow(style),
              });
              break;
            }

            ancestor = ancestor.parentElement;
          }
        }

        const viewportWidth = window.innerWidth;
        const singleLineRules: Array<{ selector: string; minWidth: number; label: string }> = lineRulesArg as Array<{
          selector: string;
          minWidth: number;
          label: string;
        }>;

        for (const lineRule of singleLineRules) {
          if (viewportWidth < lineRule.minWidth) {
            continue;
          }

          for (const element of Array.from(document.querySelectorAll<HTMLElement>(lineRule.selector))) {
            if (!isVisible(element) || !hasSubstance(element)) {
              continue;
            }

            const lines = lineCount(element);
            if (lines <= 1) {
              continue;
            }

            lineFailures.push({
              selector: selectorFor(element),
              text: textFor(element),
              reason: `${lineRule.label} rendered on ${lines} lines at ${viewportWidth}px viewport`,
              element: rectOf(element),
              lines,
            });
          }
        }

        return {
          failures: failures.slice(0, 80),
          lineFailures,
        };
            }, singleLineRules);

            const frameFailures = routeFailures.failures || [];
            const lineRuleFailures = routeFailures.lineFailures || [];
            const routeNetworkViolations = networkViolations(page);
            const routeFailureCount = frameFailures.length
              + lineRuleFailures.length
              + routeNetworkViolations.length;

            failures.push(...frameFailures.map((failure) => ({
              route,
              viewport: viewport.name,
              ...failure,
            })));

            failures.push(...lineRuleFailures.map((failure) => ({
              route,
              viewport: viewport.name,
              selector: failure.selector,
              text: failure.text,
              reason: failure.reason,
              element: failure.element,
              frame: undefined,
              frameOverflow: `line-count:${failure.lines}`,
            })));

            failures.push(...routeNetworkViolations.map((violation) => ({
              route,
              viewport: viewport.name,
              selector: 'network',
              text: violation.url.slice(0, 140),
              reason: `${violation.reason}: ${violation.method} ${violation.url}`,
              element: { x: 0, y: 0, width: 0, height: 0, right: 0, bottom: 0 },
            })));

            pageResults.push({
              route,
              viewport: viewport.name,
              status,
              failure_count: routeFailureCount,
              page_closure_retries: pageClosureRetries,
              candidate_identity_verified: true,
              network_violation_count: routeNetworkViolations.length,
            });
            routeCompleted = true;
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            const transientPageClosure = transientPageClosureNeedles.some((needle) => message.includes(needle));
            if (!transientPageClosure || pageClosureRetries >= 2) {
              throw error;
            }

            pageClosureRetries += 1;
            pageResults.push({
              route,
              viewport: viewport.name,
              status: 'retry',
              retry_reason: 'page_or_browser_closed',
              retry_attempt: pageClosureRetries,
            });
            await auditBrowser.close().catch(() => {});
            auditBrowser = await launchAuditBrowser(playwright, browserName);
          } finally {
            await closeAuditedPage(page);
          }
        }
      }
    }
  } finally {
    await auditBrowser.close().catch(() => {});
  }

  const payload = {
    contract_name: 'chummer.ui-frame-integrity/v2',
    contract_version: 2,
    generated_at_utc: new Date().toISOString(),
    route_matrix_started_at_utc: routeMatrixStartedAtUtc,
    base_url: candidateBinding.baseUrl,
    request_methods: ['GET'],
    candidate_binding: candidateBindingReceipt(candidateBinding),
    authority_observation: authorityObservation,
    release_version: candidateBinding.releaseVersion,
    manifest_sha256: candidateBinding.manifestSha256,
    authority_snapshot_sha256: candidateBinding.authoritySnapshotSha256,
    release_decision_sha256: candidateBinding.releaseDecisionSha256,
    release_scope_decision_sha256: candidateBinding.releaseScopeDecisionSha256,
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    routes: routeViewportMatrix.map((scenario) => scenario.route),
    viewports,
    route_viewport_matrix: routeViewportMatrix,
    summary: {
      checked_pages: pageResults.length,
      failure_count: failures.length,
    },
    failures,
    pages: pageResults,
  };

  completedFrameReport = [
    '# UI Frame Integrity Gate',
    '',
    `- Generated: ${payload.generated_at_utc}`,
    `- Base URL: ${candidateBinding.baseUrl}`,
    `- Release version: ${candidateBinding.releaseVersion}`,
    `- Manifest SHA-256: ${candidateBinding.manifestSha256}`,
    `- Authority snapshot SHA-256: ${candidateBinding.authoritySnapshotSha256}`,
    `- Release decision SHA-256: ${candidateBinding.releaseDecisionSha256}`,
    `- Release-scope decision SHA-256: ${candidateBinding.releaseScopeDecisionSha256}`,
    `- Status: ${payload.status}`,
    `- Checked pages: ${pageResults.length}`,
    `- Failures: ${failures.length}`,
    '',
    ...failures.slice(0, 40).map((failure) => `- ${failure.viewport} ${failure.route} ${failure.selector}: ${failure.reason}`),
  ].join('\n');
  completedFramePayload = payload;

  expect(failures, failures.map((failure) => `${failure.viewport} ${failure.route} ${failure.selector}: ${failure.reason} (${failure.text})`).join('\n')).toEqual([]);
});

test('login stays compact and does not reintroduce the old visual hero', async ({ playwright, browserName }) => {
  test.setTimeout(90000);
  const failures: Array<string> = [];
  const checked: Array<Record<string, unknown>> = [];
  const auditBrowser = await launchAuditBrowser(playwright, browserName);

  try {
    for (const viewport of [
      { name: 'phone-390', width: 390, height: 844 },
      { name: 'desktop-1366', width: 1366, height: 768 },
    ]) {
      const page = await createAuditedPage(auditBrowser, { width: viewport.width, height: viewport.height });
      try {
        const response = await gotoWithRetry(page, '/login?next=%2Faccount%2Faccess');
        await verifyCandidateNavigationResponse(
          page,
          response,
          '/login?next=%2Faccount%2Faccess',
        );

        const panel = page.locator('.auth-panel--entry').first();
        await expect(panel).toBeVisible();
        await expect(page.locator('body')).toContainText('Open Chummer');
        const bodyText = await page.locator('body').innerText();
        const emailFieldCount = await page.locator('input[type="email"]').count();
        if (emailFieldCount > 0) {
          await expect(page.locator('body')).toContainText('Email first. Google if you prefer.');
          await expect(page.locator('input[type="email"]')).toBeVisible();
          await expect(page.getByRole('button', { name: 'Continue with email' })).toBeVisible();
        } else {
          expect(bodyText).not.toContain('Email first. Google if you prefer.');
          await expect(page.getByRole('link', { name: 'Continue with Google' })).toBeVisible();
        }

        const metrics = await page.evaluate(() => {
      const panel = document.querySelector<HTMLElement>('.auth-panel--entry');
      const entry = document.querySelector<HTMLElement>('.auth-entry');
      const header = document.querySelector<HTMLElement>('[data-site-header]');
      const footer = document.querySelector<HTMLElement>('.site-footer');
      const visualCount = document.querySelectorAll('.auth-visual, .auth-entry__story--visual, picture, img').length;
      const compactSheet = Array.from(document.styleSheets).some((sheet) => String(sheet.href || '').includes('/css/auth-compact.css'));
      const panelRect = panel?.getBoundingClientRect();
      const entryRect = entry?.getBoundingClientRect();
      const headerVisible = header ? getComputedStyle(header).display !== 'none' : false;
      const footerVisible = footer ? getComputedStyle(footer).display !== 'none' : false;

      return {
        visualCount,
        compactSheet,
        headerVisible,
        footerVisible,
        documentOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        panelWidth: panelRect?.width ?? 0,
        panelHeight: panelRect?.height ?? 0,
        entryWidth: entryRect?.width ?? 0,
        entryHeight: entryRect?.height ?? 0,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      };
    });

        if (!metrics.compactSheet) {
          failures.push(`${viewport.name}: auth-compact stylesheet was not loaded`);
        }
        if (metrics.visualCount !== 0) {
          failures.push(`${viewport.name}: login rendered ${metrics.visualCount} image/visual hero node(s)`);
        }
        if (metrics.headerVisible || metrics.footerVisible) {
          failures.push(`${viewport.name}: login chrome should stay hidden for the compact sign-in surface`);
        }
        if (metrics.documentOverflowX > 1) {
          failures.push(`${viewport.name}: login has ${Math.round(metrics.documentOverflowX)}px horizontal overflow`);
        }
        if (metrics.entryWidth > Math.min(360, metrics.viewportWidth)) {
          failures.push(`${viewport.name}: login entry is wider than the compact limit (${Math.round(metrics.entryWidth)}px)`);
        }
        if (metrics.entryHeight > metrics.viewportHeight - 24) {
          failures.push(`${viewport.name}: login entry does not fit in one viewport (${Math.round(metrics.entryHeight)}px of ${metrics.viewportHeight}px)`);
        }
        if (metrics.panelHeight > metrics.viewportHeight - 24) {
          failures.push(`${viewport.name}: login panel does not fit in one viewport (${Math.round(metrics.panelHeight)}px of ${metrics.viewportHeight}px)`);
        }

        checked.push({ viewport: viewport.name, ...metrics });
        for (const violation of networkViolations(page)) {
          failures.push(
            `${viewport.name}: ${violation.reason}: ${violation.method} ${violation.url}`,
          );
        }
      } finally {
        await closeAuditedPage(page);
      }
    }
  } finally {
    await auditBrowser.close().catch(() => {});
  }

  completedLoginPayload = {
    contract_name: 'chummer.login-compact-frame/v2',
    contract_version: 2,
    generated_at_utc: new Date().toISOString(),
    base_url: candidateBinding.baseUrl,
    request_methods: ['GET'],
    candidate_binding: candidateBindingReceipt(candidateBinding),
    authority_observation: authorityObservation,
    status: failures.length === 0 ? 'pass' : 'fail',
    checked,
    failures,
  };

  expect(failures).toEqual([]);
});
