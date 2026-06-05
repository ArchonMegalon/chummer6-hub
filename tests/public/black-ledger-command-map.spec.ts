import { test, expect } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger command map renders with routes, controls, and fallback content', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });

  const root = page.locator('#ledger-map [data-black-ledger-geoscape-root]').first();
  await expect(root).toBeVisible();
  await expect(root.locator('.black-ledger-geoscape__canvas')).toBeVisible();
  await expect(root.getByRole('button', { name: 'Influence' })).toBeVisible();
  await expect(root.getByRole('button', { name: 'Replay pressure' })).toBeVisible();
  await expect(root.locator('.black-ledger-geoscape__panel')).toBeVisible();
  await expect(root.locator('.black-ledger-geoscape__fallback-list')).toBeVisible();

  const geometry = await root.evaluate((element) => {
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

  const eventCount = await root.locator('.black-ledger-geoscape__list--static li').count();
  const factionCount = Number(await root.getAttribute('data-faction-count'));
  const districtCount = Number(await root.getAttribute('data-district-count'));
  expect(factionCount).toBeGreaterThanOrEqual(6);
  expect(districtCount).toBeGreaterThanOrEqual(8);
  expect(geometry.stage).not.toBeNull();
  expect(geometry.overlay).not.toBeNull();
  expect(geometry.signalRail).not.toBeNull();
  expect(geometry.panel).not.toBeNull();
  expect(geometry.controls).not.toBeNull();
  expect((geometry.controls?.y ?? 0)).toBeGreaterThanOrEqual((geometry.stage?.bottom ?? 0) - 1);

  writeJsonArtifact('BLACK_LEDGER_GLOBE_RENDER.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map',
    event_count: eventCount,
    faction_count: factionCount,
    district_count: districtCount,
    geometry,
    renderer: await root.getAttribute('data-renderer'),
    fallback_present: await root.locator('.black-ledger-geoscape__fallback-list').count(),
  });
});
