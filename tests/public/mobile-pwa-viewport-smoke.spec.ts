import { expect, test, type Page } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

type BuildLayout = 'compact' | 'workspace';

type ViewportExpectation = {
  name: string;
  width: number;
  height: number;
  expectedBuildLayout: BuildLayout;
};

type RouteExpectation = {
  path: string;
  expectedHeading: string | null;
  requiredSelectors: string[];
  requiredText: string[];
  surface?: 'build-pwa';
};

const viewports: ViewportExpectation[] = [
  { name: 'phone-390', width: 390, height: 844, expectedBuildLayout: 'compact' },
  { name: 'tablet', width: 768, height: 1024, expectedBuildLayout: 'compact' },
  { name: 'desktop-1366', width: 1366, height: 768, expectedBuildLayout: 'workspace' },
];

const routes: RouteExpectation[] = [
  {
    path: '/mobile',
    expectedHeading: 'Keep your runner ready at the table.',
    requiredSelectors: ['[data-play-surface="install-only"]', '[data-mobile-app-inline-qr]'],
    requiredText: ['Install app'],
  },
  {
    path: '/mobile/player',
    expectedHeading: 'Keep your runner ready at the table.',
    requiredSelectors: ['[data-play-surface="install-only"]', '[data-mobile-app-inline-qr]'],
    requiredText: ['Install app'],
  },
  {
    path: '/mobile/gm',
    expectedHeading: 'Stage the table without exposing Game Master controls.',
    requiredSelectors: ['[data-play-surface="install-only"]', '[data-mobile-app-inline-qr]'],
    requiredText: ['Install app'],
  },
  {
    path: '/mobile/observer',
    expectedHeading: 'Follow the table without gaining control.',
    requiredSelectors: ['[data-play-surface="install-only"]', '[data-mobile-app-inline-qr]'],
    requiredText: ['Install app'],
  },
  {
    path: '/play',
    expectedHeading: 'Keep your runner ready at the table.',
    requiredSelectors: ['[data-play-surface="install-only"]', '[data-mobile-app-inline-qr]'],
    requiredText: ['Install app'],
  },
  {
    path: '/play/continuity',
    expectedHeading: 'NEXUS-PAN continuity',
    requiredSelectors: [],
    requiredText: ['NEXUS-PAN continuity'],
  },
  {
    path: '/build',
    expectedHeading: null,
    requiredSelectors: ['.build-pwa-workspace', '[data-build-pwa-layout-picker]'],
    requiredText: ['Layout'],
    surface: 'build-pwa',
  },
];

async function assertBuildPwaResponsiveContract(
  page: Page,
  viewport: ViewportExpectation,
): Promise<Record<string, string>> {
  const workspace = page.locator('.build-pwa-workspace');
  const expectedLayout = viewport.expectedBuildLayout;
  const overrideLayout: BuildLayout = expectedLayout === 'compact' ? 'workspace' : 'compact';
  const finalUrl = new URL(page.url());

  expect(`${finalUrl.pathname}${finalUrl.search}`, '/build must open the roster-first Build PWA').toBe(
    '/blazor/app?command=character_roster',
  );
  await expect(workspace).toBeVisible({ timeout: 30000 });
  await expect(workspace).toHaveAttribute('data-build-pwa-layout', 'responsive');
  await expect(workspace).toHaveAttribute('data-build-pwa-layout-source', 'browser-media-query');
  await expect(workspace).toHaveAttribute('data-build-pwa-layout-preference', 'auto', { timeout: 15000 });
  await expect(workspace).toHaveAttribute('data-build-pwa-layout-effective', expectedLayout);
  await expect(workspace).toHaveClass(new RegExp(`build-pwa-layout--${expectedLayout}`));
  await expect(page.locator('[data-build-pwa-layout-choice="auto"]')).toBeChecked();
  await expect(page.locator('#build-pwa-layout-status')).toContainText(
    `Auto is using the ${expectedLayout} layout for the current browser width.`,
  );
  await expect(page.locator('#chummer-workspace-main')).toBeVisible();

  if (expectedLayout === 'compact') {
    await expect(page.locator('.build-pwa-compact-context')).toBeVisible();
    await expect(page.locator('h1#build-pwa-compact-title')).toBeVisible();
  } else {
    await expect(page.locator('.build-pwa-compact-context')).toBeHidden();
  }

  await page.locator(`[data-build-pwa-layout-choice="${overrideLayout}"]`).check();
  await expect(workspace).toHaveAttribute('data-build-pwa-layout-preference', overrideLayout);
  await expect(workspace).toHaveAttribute('data-build-pwa-layout-effective', overrideLayout);
  await expect(page.locator('#build-pwa-layout-status')).toContainText(
    `${overrideLayout === 'compact' ? 'Compact' : 'Workspace'} layout selected.`,
  );

  await page.locator('[data-build-pwa-layout-choice="auto"]').check();
  await expect(workspace).toHaveAttribute('data-build-pwa-layout-preference', 'auto');
  await expect(workspace).toHaveAttribute('data-build-pwa-layout-effective', expectedLayout);

  return {
    final_url: finalUrl.toString(),
    build_layout_source: 'browser-media-query',
    build_layout_preference: 'auto',
    build_layout_effective: expectedLayout,
    build_layout_override_checked: overrideLayout,
  };
}

test('core mobile PWA routes fit phone tablet and desktop viewports', async ({ browser }) => {
  test.setTimeout(300000);
  const results: Array<Record<string, unknown>> = [];
  const failures: string[] = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport });
    page.setDefaultTimeout(5000);
    page.setDefaultNavigationTimeout(15000);
    await page.route('**/*', async (route) => {
      if (route.request().resourceType() === 'media') {
        await route.abort();
        return;
      }

      await route.continue();
    });

    for (const route of routes) {
      let status = 0;
      let navigationError = '';
      let buildLayoutProof: Record<string, string> | null = null;
      let metrics = {
        viewportWidth: viewport.width,
        documentOverflowX: 0,
      };
      try {
        let response: Awaited<ReturnType<typeof page.goto>> = null;
        let recoveredStatus: number | null = null;
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            response = await page.goto(route.path, {
              waitUntil: 'commit',
              timeout: attempt === 0 ? 15000 : 30000,
            });
            navigationError = '';
            break;
          } catch (error) {
            navigationError = error instanceof Error ? error.message : String(error);
            const currentPath = new URL(page.url()).pathname;
            const sameRouteNavigation = navigationError.includes('interrupted by another navigation')
              && navigationError.includes(`"${baseUrl}${route.path}"`)
              && currentPath === route.path;
            if (sameRouteNavigation) {
              const fallbackResponse = await page.request.get(new URL(route.path, baseUrl).toString());
              recoveredStatus = fallbackResponse.status();
              navigationError = '';
              break;
            }
            if (attempt === 0) {
              await page.waitForTimeout(1000);
            }
          }
        }
        if (!response && recoveredStatus === null && navigationError) {
          throw new Error(navigationError);
        }
        status = response?.status() ?? recoveredStatus ?? 0;
        if (route.surface === 'build-pwa') {
          buildLayoutProof = await assertBuildPwaResponsiveContract(page, viewport);
        } else if (route.expectedHeading) {
          await page.waitForFunction(
            (expectedHeading) => {
              const bodyText = document.body?.innerText || '';
              const title = document.title || '';
              return bodyText.includes(expectedHeading)
                || title.includes('Chummer Mobile Turn Companion');
            },
            route.expectedHeading,
            { timeout: 5000 },
          ).catch(() => undefined);
        }
        metrics = await page.evaluate(() => ({
          viewportWidth: window.innerWidth,
          documentOverflowX: Math.max(
            document.documentElement.scrollWidth,
            document.body?.scrollWidth || 0,
          ) - window.innerWidth,
        }));
      } catch (error) {
        navigationError = error instanceof Error ? error.message : String(error);
        failures.push(`${route.path} ${viewport.name} navigation failed: ${navigationError}`);
      }

      const result = {
        route: route.path,
        viewport: viewport.name,
        width: viewport.width,
        height: viewport.height,
        status,
        overflow_x: metrics.documentOverflowX,
        navigation_error: navigationError,
        ...(buildLayoutProof ?? {}),
      };
      results.push(result);

      if (status >= 500) {
        failures.push(`${route.path} ${viewport.name} returned HTTP ${status}`);
      }

      if (metrics.documentOverflowX > 1) {
        failures.push(`${route.path} ${viewport.name} has ${Math.round(metrics.documentOverflowX)}px horizontal overflow`);
      }

      const headingVisible = route.expectedHeading
        ? await page.getByRole('heading', { name: route.expectedHeading }).isVisible({ timeout: 5000 }).catch(() => false)
        : true;
      const bodyText = await page.locator('body').textContent({ timeout: 5000 }).catch(() => '');
      if (route.expectedHeading && !headingVisible) {
        failures.push(`${route.path} ${viewport.name} missing heading ${route.expectedHeading}`);
      }

      for (const selector of route.requiredSelectors) {
        const selectorVisible = await page.locator(selector).isVisible({ timeout: 5000 }).catch(() => false);
        if (!selectorVisible) {
          failures.push(`${route.path} ${viewport.name} missing selector ${selector}`);
        }
      }
      for (const text of route.requiredText) {
        const textPresent = bodyText?.includes(text)
          || (text === 'Install app' && bodyText?.includes('Add to Home Screen'));
        if (!textPresent) {
          failures.push(`${route.path} ${viewport.name} missing text ${text}`);
        }
      }
    }

    await page.close();
  }

  writeJsonArtifact('MOBILE_PWA_VIEWPORT_SMOKE.generated.json', {
    contractName: 'chummer.mobile_pwa_viewport_smoke.v1',
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    base_url: baseUrl,
    routes: routes.map((route) => route.path),
    route_count: routes.length,
    viewport_count: viewports.length,
    results,
    failures,
  });

  expect(failures).toEqual([]);
});
