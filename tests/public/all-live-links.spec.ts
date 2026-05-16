import { expect, request, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = 'https://chummer.run';
const routes = [
  '/',
  '/downloads',
  '/packages',
  '/ledger',
  '/feedback',
  '/status',
  '/mobile',
  '/karma-forge',
  '/help',
  '/contact',
  '/roadmap',
  '/changelog',
];

const genericLabels = new Set([
  'click here',
  'here',
  'learn more',
  'more',
  'open',
  'go',
  'read more',
]);

type AuditRow = {
  source_page: string;
  selector: string;
  role: string;
  interaction_class: 'inline' | 'button_like';
  visible_text: string;
  accessible_name: string;
  href_or_action: string | null;
  bounding_box: { x: number; y: number; width: number; height: number } | null;
  visible: boolean;
  enabled: boolean;
  focusable: boolean;
  tab_reachable: boolean;
  tap_target_size: { width: number; height: number } | null;
  final_url: string | null;
  status: number | null;
  auth_redirect_expected: boolean;
  hash_target_exists: boolean | null;
  result: 'pass' | 'fail';
  failures: string[];
};

function normalizeLabel(value: string): string {
  return value.replace(/\s+/g, ' ').trim().toLowerCase();
}

function isExternal(url: string): boolean {
  try {
    return new URL(url, baseUrl).origin !== baseUrl;
  } catch {
    return false;
  }
}

function isAuthRedirect(pathname: string): boolean {
  return pathname.startsWith('/login') || pathname.startsWith('/auth/');
}

function isButtonLike(meta: {
  tagName: string;
  role: string;
  className: string;
  hrefOrAction: string | null;
}): boolean {
  if (meta.tagName === 'button' || meta.tagName === 'form') {
    return true;
  }
  if (meta.tagName === 'input') {
    return true;
  }
  if (meta.role === 'button') {
    return true;
  }
  if (/\bbutton-like\b|\bcta\b|\bcard-link\b|\bnav-link\b|\bsite-sidebar__nav\b/i.test(meta.className)) {
    return true;
  }
  if (meta.tagName === 'a' && meta.hrefOrAction) {
    if (/^#/.test(meta.hrefOrAction)) {
      return false;
    }
    if (/\blaunch-hero__action\b|\bpath-card\b|\baccount-value__action\b|\bpreview-card\b/i.test(meta.className)) {
      return true;
    }
  }
  return false;
}

function isIntrinsicFocusable(meta: {
  tagName: string;
  hrefOrAction: string | null;
  enabled: boolean;
}): boolean {
  if (!meta.enabled) {
    return false;
  }
  if (meta.tagName === 'button' || meta.tagName === 'input' || meta.tagName === 'select' || meta.tagName === 'textarea') {
    return true;
  }
  if (meta.tagName === 'a') {
    return !!meta.hrefOrAction;
  }
  return false;
}

test('all visible public links and actions stay usable in the rendered DOM', async ({ browser }) => {
  test.setTimeout(180000);
  const api = await request.newContext();
  const checkedUrls = new Map<string, { status: number; finalUrl: string }>();
  const rows: AuditRow[] = [];
  const failures: string[] = [];

  for (const route of routes) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport: { width: 1366, height: 768 } });
    const response = await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded' });
    expect(response, `${route} should load`).not.toBeNull();
    expect(response!.status(), `${route} should load`).toBeLessThan(400);

    const locator = page.locator('a, button, [role="button"], input[type="submit"], input[type="button"], form');
    const count = await locator.count();

    for (let index = 0; index < count; index += 1) {
      const handle = locator.nth(index);
      const meta = await handle.evaluate((element, i) => {
        const htmlElement = element as HTMLElement;
        const rect = htmlElement.getBoundingClientRect();
        const text = (htmlElement.innerText || htmlElement.textContent || '').replace(/\s+/g, ' ').trim();
        const aria = htmlElement.getAttribute('aria-label') || '';
        const title = htmlElement.getAttribute('title') || '';
        const accessibleName = (aria || title || text).replace(/\s+/g, ' ').trim();
        const role = htmlElement.getAttribute('role') || element.tagName.toLowerCase();
        const href = htmlElement.getAttribute('href');
        const action = htmlElement.getAttribute('action');
        const rel = htmlElement.getAttribute('rel') || '';
        const target = htmlElement.getAttribute('target') || '';
        const className = htmlElement.className || '';
        const selector = `${element.tagName.toLowerCase()}[data-ux-index="${i}"]`;
        const focusable = !htmlElement.hasAttribute('disabled')
          && htmlElement.tabIndex >= 0
          && !htmlElement.hasAttribute('aria-hidden');
        return {
          selector,
          role,
          visibleText: text,
          accessibleName,
          hrefOrAction: href || action,
          rel,
          target,
          className,
          tagName: element.tagName.toLowerCase(),
          visible: !!(rect.width > 0 && rect.height > 0),
          enabled: !(htmlElement as HTMLButtonElement).disabled,
          focusable,
          boundingBox: rect.width > 0 && rect.height > 0
            ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
            : null,
        };
      }, index);

      if (!meta.visible) {
        continue;
      }

      const row: AuditRow = {
        source_page: route,
        selector: meta.selector,
        role: meta.role,
        interaction_class: isButtonLike(meta) ? 'button_like' : 'inline',
        visible_text: meta.visibleText,
        accessible_name: meta.accessibleName,
        href_or_action: meta.hrefOrAction,
        bounding_box: meta.boundingBox,
        visible: meta.visible,
        enabled: meta.enabled,
        focusable: meta.focusable,
        tab_reachable: false,
        tap_target_size: meta.boundingBox ? { width: meta.boundingBox.width, height: meta.boundingBox.height } : null,
        final_url: null,
        status: null,
        auth_redirect_expected: false,
        hash_target_exists: null,
        result: 'pass',
        failures: [],
      };

      if (!meta.accessibleName) {
        row.failures.push('missing accessible name');
      }

      if (genericLabels.has(normalizeLabel(meta.accessibleName))) {
        row.failures.push(`generic label: ${meta.accessibleName}`);
      }

      if (meta.tagName === 'form') {
        row.tab_reachable = true;
      } else if (!meta.focusable || !isIntrinsicFocusable(meta)) {
        row.failures.push('visible interactive element is not keyboard focusable');
      } else if (row.interaction_class === 'button_like') {
        await handle.focus();
        row.tab_reachable = await handle.evaluate((element) => document.activeElement === element);
        if (!row.tab_reachable && (meta.tagName === 'button' || meta.role === 'button')) {
          row.failures.push('focus() did not move active element to the clickable control');
        }
      } else {
        row.tab_reachable = true;
      }

      if (
        row.interaction_class === 'button_like'
        && row.tap_target_size
        && (row.tap_target_size.width < 44 || row.tap_target_size.height < 44)
      ) {
        row.failures.push(`tap target below 44x44 (${Math.round(row.tap_target_size.width)}x${Math.round(row.tap_target_size.height)})`);
      }

      const destination = meta.hrefOrAction?.trim() || '';
      if ((meta.tagName === 'a' || meta.tagName === 'form') && !destination) {
        row.failures.push('missing href/action');
      }

      if (destination === '#') {
        row.failures.push('href/action is bare #');
      }

      if (destination.startsWith('javascript:')) {
        row.failures.push('javascript pseudo-link exposed publicly');
      }

      if (destination.includes('/admin/') || destination.includes('/api/internal/')) {
        row.failures.push(`operator/internal route linked publicly: ${destination}`);
      }

      if (destination.startsWith('#')) {
        const targetId = destination.slice(1);
        row.hash_target_exists = targetId.length > 0
          ? await page.locator(`#${targetId}, [name="${targetId}"]`).count() > 0
          : false;
        if (!row.hash_target_exists) {
          row.failures.push(`missing hash target: ${destination}`);
        }
      } else if (destination) {
        const resolved = new URL(destination, `${baseUrl}${route}`);
        if (resolved.protocol === 'mailto:' || resolved.protocol === 'tel:') {
          row.final_url = resolved.toString();
        } else if (isExternal(resolved.toString())) {
          row.final_url = resolved.toString();
          if (!meta.rel.includes('noopener') || !meta.rel.includes('noreferrer')) {
            row.failures.push('external link missing rel=noopener noreferrer');
          }
        } else {
          const normalized = resolved.toString();
          row.auth_redirect_expected = isAuthRedirect(resolved.pathname);
          if (!checkedUrls.has(normalized)) {
            const linkResponse = await api.get(normalized, { maxRedirects: 5 });
            checkedUrls.set(normalized, {
              status: linkResponse.status(),
              finalUrl: linkResponse.url(),
            });
          }
          const checked = checkedUrls.get(normalized)!;
          row.status = checked.status;
          row.final_url = checked.finalUrl;
          if (checked.status >= 400) {
            row.failures.push(`broken route status ${checked.status}`);
          }
        }
      }

      if (row.failures.length > 0) {
        row.result = 'fail';
        failures.push(`${route} ${meta.role} ${meta.accessibleName || meta.visibleText || destination || '<unnamed>'}: ${row.failures.join('; ')}`);
      }

      rows.push(row);
    }

    await page.close();
  }

  writeJsonArtifact('LIVE_LINK_AUDIT.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    audited_routes: routes,
    element_count: rows.length,
    issues_found: failures.length,
    failures,
    rows,
  });

  expect(failures, failures.join('\n')).toEqual([]);
});
