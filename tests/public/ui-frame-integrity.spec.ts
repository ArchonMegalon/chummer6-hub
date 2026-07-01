import { expect, test } from 'playwright/test';
import { writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

const routes = [
  '/',
  '/downloads',
  '/status',
  '/faq',
  '/ledger',
  '/ledger/map',
  '/packages',
  '/feedback',
  '/docs/embed/origin-dossier-the-name-she-chose',
  '/login?next=%2Faccount%2Faccess',
  '/account/access/install-link?installationId=ins-ui-gate&headId=avalonia&applicationVersion=run-20260612-121055&releaseChannel=docker&platform=windows&arch=x64&installLinkMode=browser_callback&installLinkTransport=grant_callback&installLinkCallbackUri=chummer%3A%2F%2Finstall-link',
];

const viewports = [
  { name: 'phone-390', width: 390, height: 844 },
  { name: 'phone-412', width: 412, height: 915 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop-1366', width: 1366, height: 768 },
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'wide', width: 1920, height: 1080 },
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

test('public UI elements are not cut off by their frames outside intentional scroll panels', async ({ browser }) => {
  test.setTimeout(matrixTimeoutMs);
  const failures: FrameFailure[] = [];
  const pageResults: Array<Record<string, unknown>> = [];

  for (const viewport of viewports) {
    for (const route of routes) {
      const page = await browser.newPage({ baseURL: baseUrl, viewport: { width: viewport.width, height: viewport.height } });
      await page.route('**/*', async (requestRoute) => {
        const resourceType = requestRoute.request().resourceType();
        if (resourceType === 'media') {
          await requestRoute.abort();
          return;
        }

        await requestRoute.continue();
      });
      await page.addInitScript(() => {
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

      const response = await gotoWithRetry(page, route);

      const status = response?.status() ?? 0;
      if (status >= 500) {
        failures.push({
          route,
          viewport: viewport.name,
          selector: 'document',
          text: '',
          reason: `route returned HTTP ${status}`,
          element: { x: 0, y: 0, width: 0, height: 0, right: 0, bottom: 0 },
        });
        await page.close().catch(() => {});
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
      const routeFailureCount = frameFailures.length + lineRuleFailures.length;

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

      pageResults.push({
        route,
        viewport: viewport.name,
        status,
        failure_count: routeFailureCount,
      });
      await page.close().catch(() => {});
    }
  }

  const payload = {
    generated_at_utc: new Date().toISOString(),
    base_url: baseUrl,
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    routes,
    viewports,
    summary: {
      checked_pages: pageResults.length,
      failure_count: failures.length,
    },
    failures,
    pages: pageResults,
  };

  writeJsonArtifact('UI_FRAME_INTEGRITY.generated.json', payload);
  writeMarkdownArtifact('UI_FRAME_INTEGRITY_REPORT.md', [
    '# UI Frame Integrity Gate',
    '',
    `- Generated: ${payload.generated_at_utc}`,
    `- Base URL: ${baseUrl}`,
    `- Status: ${payload.status}`,
    `- Checked pages: ${pageResults.length}`,
    `- Failures: ${failures.length}`,
    '',
    ...failures.slice(0, 40).map((failure) => `- ${failure.viewport} ${failure.route} ${failure.selector}: ${failure.reason}`),
  ].join('\n'));

  expect(failures, failures.map((failure) => `${failure.viewport} ${failure.route} ${failure.selector}: ${failure.reason} (${failure.text})`).join('\n')).toEqual([]);
});

test('login stays compact and does not reintroduce the old visual hero', async ({ browser }) => {
  test.setTimeout(90000);
  const failures: Array<string> = [];
  const checked: Array<Record<string, unknown>> = [];

  for (const viewport of [
    { name: 'phone-390', width: 390, height: 844 },
    { name: 'desktop-1366', width: 1366, height: 768 },
  ]) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport: { width: viewport.width, height: viewport.height } });
    await page.route('**/*', async (requestRoute) => {
      const resourceType = requestRoute.request().resourceType();
      if (resourceType === 'media') {
        await requestRoute.abort();
        return;
      }

      await requestRoute.continue();
    });

    const response = await gotoWithRetry(page, '/login?next=%2Faccount%2Faccess');
    expect(response?.status() ?? 0).toBeLessThan(500);

    const panel = page.locator('.auth-panel--entry').first();
    await expect(panel).toBeVisible();
    await expect(page.locator('body')).toContainText('Open Chummer');
    await expect(page.locator('body')).toContainText('Email first. Google if you prefer.');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue with email' })).toBeVisible();

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
    await page.close().catch(() => {});
  }

  writeJsonArtifact('LOGIN_COMPACT_FRAME.generated.json', {
    generated_at_utc: new Date().toISOString(),
    base_url: baseUrl,
    status: failures.length === 0 ? 'pass' : 'fail',
    checked,
    failures,
  });

  expect(failures).toEqual([]);
});
