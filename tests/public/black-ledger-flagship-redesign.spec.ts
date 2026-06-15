import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

type RectSnapshot = { x: number; y: number; width: number; height: number; right: number; bottom: number; area: number };

function intersectionArea(left: RectSnapshot, right: RectSnapshot): number {
  const width = Math.max(0, Math.min(left.right, right.right) - Math.max(left.x, right.x));
  const height = Math.max(0, Math.min(left.bottom, right.bottom) - Math.max(left.y, right.y));
  return width * height;
}

test('black ledger route opens as a command deck without clipped flagship copy', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'domcontentloaded' });

  const deck = page.locator('[data-ledger-redesign="command-deck"]');
  const title = deck.locator('h1.page-title');
  const globe = deck.locator('[data-black-ledger-geoscape-root]');
  const actions = deck.locator('.ledger-flagship__actions a');
  const stage = globe.locator('[data-geoscape-stage]');
  const overlay = globe.locator('[data-geoscape-overlay]');
  const signalRail = globe.locator('[data-geoscape-signal-rail]');
  const panel = globe.locator('[data-geoscape-panel]');
  const controls = globe.locator('[data-geoscape-controls]');

  await expect(deck).toBeVisible();
  await expect(globe).toHaveAttribute('data-ready', 'true');
  await expect(actions).toHaveCount(3);
  await expect(stage).toBeVisible();
  await expect(overlay).toBeVisible();
  await expect(signalRail).toBeVisible();
  await expect(panel).toBeVisible();
  await expect(controls).toBeVisible();
  const actionHrefs = await actions.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).getAttribute('href') ?? ''));
  expect(actionHrefs).toContain('/ledger/map#ledger-map');
  expect(actionHrefs).toContain('/ledger/newsroom');

  const fit = await title.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const parentBounds = element.parentElement?.getBoundingClientRect();
    return {
      titleWidth: bounds.width,
      parentWidth: parentBounds?.width ?? 0,
      titleRight: bounds.right,
      parentRight: parentBounds?.right ?? 0,
      lineHeight: Number.parseFloat(getComputedStyle(element).lineHeight),
      height: bounds.height,
    };
  });

  expect(fit.titleWidth).toBeLessThanOrEqual(fit.parentWidth);
  expect(fit.titleRight).toBeLessThanOrEqual(fit.parentRight + 1);
  expect(fit.height / fit.lineHeight).toBeLessThanOrEqual(4.2);

  const geometry = await deck.evaluate((element) => {
    function readRect(selector: string) {
      const node = element.querySelector(selector) as HTMLElement | null;
      const rect = node?.getBoundingClientRect();
      return rect
        ? {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            right: rect.right,
            bottom: rect.bottom,
            area: rect.width * rect.height,
          }
        : null;
    }

    return {
      stage: readRect('[data-geoscape-stage]'),
      overlay: readRect('[data-geoscape-overlay]'),
      signalRail: readRect('[data-geoscape-signal-rail]'),
      panel: readRect('[data-geoscape-panel]'),
      controls: readRect('[data-geoscape-controls]'),
    };
  });

  expect(geometry.stage).not.toBeNull();
  expect(geometry.overlay).not.toBeNull();
  expect(geometry.signalRail).not.toBeNull();
  expect(geometry.panel).not.toBeNull();
  expect(geometry.controls).not.toBeNull();

  const stageRect = geometry.stage as RectSnapshot;
  const overlayRect = geometry.overlay as RectSnapshot;
  const signalRect = geometry.signalRail as RectSnapshot;
  const panelRect = geometry.panel as RectSnapshot;
  const controlsRect = geometry.controls as RectSnapshot;

  expect(intersectionArea(overlayRect, panelRect)).toBe(0);
  expect(intersectionArea(overlayRect, signalRect)).toBe(0);
  expect(intersectionArea(panelRect, signalRect)).toBe(0);
  expect(intersectionArea(stageRect, panelRect) / panelRect.area).toBeLessThan(0.3);
  expect(intersectionArea(stageRect, signalRect) / signalRect.area).toBeGreaterThan(0.9);
  expect(controlsRect.y).toBeGreaterThanOrEqual(stageRect.bottom - 1);

  const centralSafeZone: RectSnapshot = {
    x: stageRect.x + stageRect.width * 0.22,
    y: stageRect.y + stageRect.height * 0.18,
    width: stageRect.width * 0.56,
    height: stageRect.height * 0.52,
    right: stageRect.x + stageRect.width * 0.78,
    bottom: stageRect.y + stageRect.height * 0.7,
    area: stageRect.width * 0.56 * stageRect.height * 0.52,
  };
  const centralOcclusion = intersectionArea(centralSafeZone, overlayRect)
    + intersectionArea(centralSafeZone, signalRect)
    + intersectionArea(centralSafeZone, panelRect);

  expect(centralOcclusion / centralSafeZone.area).toBeLessThan(0.08);

  writeJsonArtifact('BLACK_LEDGER_FLAGSHIP_REDESIGN.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    desktop_title_fit: fit,
    desktop_geometry: geometry,
    central_safe_zone_occlusion_ratio: centralOcclusion / centralSafeZone.area,
  });
});

test('black ledger mobile first screen reaches the globe', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/ledger`, { waitUntil: 'domcontentloaded' });

  const globe = page.locator('[data-ledger-redesign="command-deck"] [data-black-ledger-geoscape-root]').first();
  const stage = globe.locator('[data-geoscape-stage]');
  const overlay = globe.locator('[data-geoscape-overlay]');
  const signalRail = globe.locator('[data-geoscape-signal-rail]');
  const controls = globe.locator('[data-geoscape-controls]');
  await expect(globe).toHaveAttribute('data-ready', 'true');
  await expect(stage).toBeVisible();
  await expect(overlay).toBeVisible();
  await expect(signalRail).toBeVisible();
  await expect(controls).toBeVisible();

  const box = await globe.boundingBox();
  expect(box?.y ?? Number.POSITIVE_INFINITY).toBeLessThan(844);
  expect(box?.height ?? 0).toBeGreaterThan(460);

  const mobileGeometry = await globe.evaluate((element) => {
    function readRect(selector: string) {
      const node = element.querySelector(selector) as HTMLElement | null;
      const rect = node?.getBoundingClientRect();
      return rect
        ? {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            right: rect.right,
            bottom: rect.bottom,
            area: rect.width * rect.height,
          }
        : null;
    }

    return {
      stage: readRect('[data-geoscape-stage]'),
      overlay: readRect('[data-geoscape-overlay]'),
      signalRail: readRect('[data-geoscape-signal-rail]'),
      controls: readRect('[data-geoscape-controls]'),
    };
  });

  const mobileStage = mobileGeometry.stage as RectSnapshot;
  const mobileOverlay = mobileGeometry.overlay as RectSnapshot;
  const mobileSignal = mobileGeometry.signalRail as RectSnapshot;
  const mobileControls = mobileGeometry.controls as RectSnapshot;

  expect(intersectionArea(mobileOverlay, mobileSignal)).toBe(0);
  expect(mobileSignal.bottom).toBeLessThanOrEqual(mobileStage.bottom + 1);
  expect(mobileControls.y).toBeGreaterThanOrEqual(mobileStage.bottom - 1);
});
