import { expect, test } from 'playwright/test';
import { completionPath, writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const homepageViewports = [
  { width: 390, height: 844 },
  { width: 412, height: 915 },
  { width: 768, height: 1024 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];
const supportingSurfaceViewports = [
  { width: 390, height: 844 },
  { width: 1366, height: 768 },
];

const supportingSurfaces = [
  {
    id: 'downloads',
    route: '/downloads',
    screenshotPrefix: 'downloads',
    requiredText: ['Install Chummer', 'Choose the latest build for Windows or Linux.', 'Stable', 'Nightly'],
  },
  {
    id: 'status',
    route: '/status',
    screenshotPrefix: 'status',
    requiredText: ['Release status', 'The build currently available from Chummer.', 'Open downloads', 'Open support'],
  },
  {
    id: 'ledger-map',
    route: '/ledger/map',
    screenshotPrefix: 'ledger-map',
    requiredText: ['campaign city command map', 'Track who is moving first.', 'Turn 2'],
  },
  {
    id: 'help',
    route: '/help',
    screenshotPrefix: 'help',
    requiredText: ['Get help without guessing', 'Choose the right path.'],
  },
] as const;

test('public flagship screenshots stay readable across live surfaces', async ({ browser }) => {
  test.setTimeout(180000);
  const homepageResults: Array<Record<string, unknown>> = [];
  const surfaceResults: Array<Record<string, unknown>> = [];
  const failures: string[] = [];

  for (const viewport of homepageViewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

    const heroTitle = page.locator('.minimal-hero h1');
    const primaryCta = page.locator('.minimal-hero .minimal-actions a.button-like').first();
    const footer = page.locator('[data-public-section="footer"]');
    const workflow = page.locator('[data-homepage-section="workflow"]');
    const downloads = page.locator('[data-homepage-section="downloads"]');
    const help = page.locator('[data-homepage-section="help"]');
    const sidebar = page.locator('.site-sidebar');
    const navLinks = page.locator('[aria-label="Primary navigation"] a, [aria-label="Primary navigation"] .site-sidebar__current');

    await expect(heroTitle).toContainText('Chummer');
    await expect(primaryCta).toContainText('Stable');
    await expect(workflow).toContainText('What it does');
    await expect(downloads).toContainText('Get the app');
    await expect(help).toContainText('Help');
    await expect(footer).toBeVisible();

    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    if (overflow > 1) {
      failures.push(`${viewport.width}x${viewport.height}: horizontal overflow ${overflow}px`);
    }

    const heroBox = await heroTitle.boundingBox();
    const ctaBox = await primaryCta.boundingBox();
    if (!heroBox || !ctaBox) {
      failures.push(`${viewport.width}x${viewport.height}: hero title or primary CTA is not visible`);
    }
    const navCount = await navLinks.count();
    if (navCount > 4) {
      failures.push(`${viewport.width}x${viewport.height}: primary navigation exposes ${navCount} links`);
    }

    const screenshotName = `homepage-${viewport.width}x${viewport.height}.png`;
    await page.screenshot({ path: completionPath(screenshotName), fullPage: true });

    homepageResults.push({
      viewport: `${viewport.width}x${viewport.height}`,
      overflow_px: overflow,
      hero_visible: !!heroBox,
      cta_visible: !!ctaBox,
      footer_visible: await footer.isVisible(),
      sidebar_visible: await sidebar.isVisible(),
      nav_panel_open: await page.evaluate(() => document.body.classList.contains('nav-panel-open')),
      screenshot: screenshotName,
      status: overflow <= 1 && heroBox && ctaBox ? 'pass' : 'fail',
    });

    await page.close();
  }

  for (const surface of supportingSurfaces) {
    for (const viewport of supportingSurfaceViewports) {
      const page = await browser.newPage({ baseURL: baseUrl, viewport });
      await page.goto(`${baseUrl}${surface.route}`, { waitUntil: 'domcontentloaded' });

      for (const marker of surface.requiredText) {
        await expect(page.locator('body')).toContainText(marker);
      }

      const overflow = await page.evaluate(() => {
        const root = document.documentElement;
        return root.scrollWidth - root.clientWidth;
      });
      if (overflow > 1) {
        failures.push(`${surface.id} ${viewport.width}x${viewport.height}: horizontal overflow ${overflow}px`);
      }

      const screenshotName = `${surface.screenshotPrefix}-${viewport.width}x${viewport.height}.png`;
      await page.screenshot({ path: completionPath(screenshotName), fullPage: true });
      surfaceResults.push({
        surface: surface.id,
        route: surface.route,
        viewport: `${viewport.width}x${viewport.height}`,
        overflow_px: overflow,
        screenshot: screenshotName,
        status: overflow <= 1 ? 'pass' : 'fail',
      });

      await page.close();
    }
  }

  writeJsonArtifact('SCREENSHOT_QA.generated.json', {
    generated_at_utc: new Date().toISOString(),
    base_url: baseUrl,
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    failures,
    homepage_results: homepageResults,
    surface_results: surfaceResults,
  });

  const lines = [
    '# Screenshot QA Report',
    '',
    `- Generated: ${new Date().toISOString()}`,
    '',
    '## Homepage',
    '',
    ...homepageResults.map((result) => `- ${result.viewport}: ${result.status}`),
    '',
    '## Supporting Surfaces',
    '',
    ...surfaceResults.map((result) => `- ${result.surface} ${result.viewport}: ${result.status}`),
  ];
  if (failures.length > 0) {
    lines.push('', '## Failures', '', ...failures.map((failure) => `- ${failure}`));
  }
  writeMarkdownArtifact('SCREENSHOT_QA_REPORT.md', lines.join('\n'));

  expect(failures, failures.join('\n')).toEqual([]);
});
