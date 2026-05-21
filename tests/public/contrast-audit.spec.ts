import { expect, test } from 'playwright/test';
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

type ContrastFinding = {
  route: string;
  state: 'normal' | 'hover' | 'focus';
  selector: string;
  text: string;
  contrast_ratio: number;
  minimum_required: number;
  font_size_px: number;
  font_weight: string;
  color: string;
  background: string;
  background_supported: boolean;
  unsupported_reason: string | null;
  manual_review_required: boolean;
  informational_review_suggested: boolean;
  screenshot_required: boolean;
};

test('public front-door surfaces meet computed contrast thresholds', async ({ browser }) => {
  test.setTimeout(180000);
  const findings: ContrastFinding[] = [];
  const failures: ContrastFinding[] = [];

  for (const route of routes) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport: { width: 1366, height: 900 } });
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });

    const collect = async (state: 'normal' | 'hover' | 'focus') => {
      const rows = await page.locator('a, button, .button-like, h1, h2, h3, h4, p, li, label, .muted-copy, .proof-chip, .site-sidebar__nav a').evaluateAll((elements, currentState) => {
        function parseColor(raw: string): [number, number, number, number] | null {
          const match = raw.match(/rgba?\\(([^)]+)\\)/i);
          if (!match) return null;
          const parts = match[1].split(',').map((part) => Number.parseFloat(part.trim()));
          if (parts.length < 3) return null;
          return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
        }
        function mix(top: [number, number, number, number], bottom: [number, number, number, number]): [number, number, number, number] {
          const alpha = top[3] + bottom[3] * (1 - top[3]);
          if (alpha <= 0) return [255, 255, 255, 1];
          return [
            ((top[0] * top[3]) + (bottom[0] * bottom[3] * (1 - top[3]))) / alpha,
            ((top[1] * top[3]) + (bottom[1] * bottom[3] * (1 - top[3]))) / alpha,
            ((top[2] * top[3]) + (bottom[2] * bottom[3] * (1 - top[3]))) / alpha,
            alpha,
          ];
        }
        function backgroundFor(element: Element): { color: string; supported: boolean; reason: string | null } {
          let current: Element | null = element;
          let composite: [number, number, number, number] = [255, 255, 255, 1];
          let sawSolidBackground = false;
          while (current) {
            const style = window.getComputedStyle(current);
            if (style.backgroundImage && style.backgroundImage !== 'none') {
              return {
                color: `rgb(${Math.round(composite[0])}, ${Math.round(composite[1])}, ${Math.round(composite[2])})`,
                supported: false,
                reason: 'background-image-or-gradient',
              };
            }
            const color = parseColor(style.backgroundColor);
            if (color && color[3] > 0) {
              sawSolidBackground = true;
              composite = mix(color, composite);
              if (composite[3] >= 0.99) {
                break;
              }
            }
            current = current.parentElement;
          }
          return {
            color: `rgb(${Math.round(composite[0])}, ${Math.round(composite[1])}, ${Math.round(composite[2])})`,
            supported: sawSolidBackground,
            reason: sawSolidBackground ? null : 'transparent-background-chain',
          };
        }
        function luminance(raw: string): number {
          const parsed = parseColor(raw);
          if (!parsed) return 1;
          const channels = parsed.slice(0, 3).map((value) => {
            const srgb = value / 255;
            return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
        }
        function contrastRatio(foreground: string, background: string): number {
          const light = Math.max(luminance(foreground), luminance(background));
          const dark = Math.min(luminance(foreground), luminance(background));
          return (light + 0.05) / (dark + 0.05);
        }
        return elements.flatMap((element, index) => {
          const htmlElement = element as HTMLElement;
          const rect = htmlElement.getBoundingClientRect();
          const text = (htmlElement.innerText || htmlElement.textContent || '').replace(/\\s+/g, ' ').trim();
          if (!text || rect.width === 0 || rect.height === 0) return [];
          const style = window.getComputedStyle(htmlElement);
          const color = style.color;
          const background = backgroundFor(htmlElement);
          const fontSize = Number.parseFloat(style.fontSize || '16');
          const fontWeight = style.fontWeight || '400';
          const numericWeight = Number.parseInt(fontWeight, 10) || 400;
          const isLarge = fontSize >= 24 || (fontSize >= 18.66 && numericWeight >= 700);
          return [{
            selector: `${element.tagName.toLowerCase()}[data-contrast-index="${index}"]`,
            state: currentState,
            text,
            contrastRatio: contrastRatio(color, background.color),
            minimumRequired: isLarge ? 3 : 4.5,
            fontSizePx: fontSize,
            fontWeight,
            color,
            background: background.color,
            backgroundSupported: background.supported,
            unsupportedReason: background.reason,
          }];
        });
      }, state);
      for (const row of rows) {
        const finding: ContrastFinding = {
          route,
          state,
          selector: row.selector,
          text: row.text,
          contrast_ratio: Number(row.contrastRatio.toFixed(2)),
          minimum_required: row.minimumRequired,
          font_size_px: Number(row.fontSizePx.toFixed(2)),
          font_weight: row.fontWeight,
          color: row.color,
          background: row.background,
          background_supported: row.backgroundSupported,
          unsupported_reason: row.unsupportedReason,
          manual_review_required: false,
          informational_review_suggested: !row.backgroundSupported,
          screenshot_required: !row.backgroundSupported,
        };
        findings.push(finding);
        if (finding.background_supported && finding.contrast_ratio + 0.01 < finding.minimum_required) {
          failures.push(finding);
        }
      }
    };

    await collect('normal');

    const firstInteractive = page.locator('a, button, .button-like').filter({ hasNotText: 'Skip to content' }).first();
    if (await firstInteractive.count() > 0) {
      await firstInteractive.scrollIntoViewIfNeeded();
      await firstInteractive.hover({ force: true });
      await collect('hover');
      await firstInteractive.focus();
      await collect('focus');
    }

    await page.close();
  }

  writeJsonArtifact('CONTRAST_AUDIT.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    finding_count: findings.length,
    review_required_count: findings.filter((finding) => finding.manual_review_required).length,
    informational_review_count: findings.filter((finding) => finding.informational_review_suggested).length,
    failure_count: failures.length,
    review_required: findings.filter((finding) => finding.manual_review_required),
    informational_review: findings.filter((finding) => finding.informational_review_suggested),
    failures,
  });

  expect(failures, JSON.stringify(failures.slice(0, 20), null, 2)).toEqual([]);
});
