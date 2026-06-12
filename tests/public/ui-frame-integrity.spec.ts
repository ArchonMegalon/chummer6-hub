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
  '/participate',
  '/feedback',
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

test('public UI elements are not cut off by their frames outside intentional scroll panels', async ({ browser }) => {
  test.setTimeout(300000);
  const failures: FrameFailure[] = [];
  const pageResults: Array<Record<string, unknown>> = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport: { width: viewport.width, height: viewport.height } });

    for (const route of routes) {
      const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

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
        continue;
      }

      const routeFailures = await page.evaluate(() => {
        type Rect = { x: number; y: number; width: number; height: number; right: number; bottom: number };
        type Failure = {
          selector: string;
          text: string;
          reason: string;
          element: Rect;
          frame?: Rect;
          frameOverflow?: string;
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
          '.launch-hero__title',
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

          return (element.innerText || element.textContent || element.getAttribute('aria-label') || '')
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

        return failures.slice(0, 80);
      });

      failures.push(...routeFailures.map((failure) => ({
        route,
        viewport: viewport.name,
        ...failure,
      })));

      pageResults.push({
        route,
        viewport: viewport.name,
        status,
        failure_count: routeFailures.length,
      });
    }

    await page.close();
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
