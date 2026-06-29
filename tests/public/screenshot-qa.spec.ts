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
    requiredText: ['Downloads', 'Stable', 'Nightly', 'Main build for this browser', 'Build from source'],
  },
  {
    id: 'status',
    route: '/status',
    screenshotPrefix: 'status',
    requiredText: ['Current release', 'Downloads', 'Help'],
  },
  {
    id: 'ledger-map',
    route: '/ledger/map',
    screenshotPrefix: 'ledger-map',
    requiredText: ['Campaign city command map', 'Track who is moving first.', 'Turn 1'],
  },
  {
    id: 'help',
    route: '/help',
    screenshotPrefix: 'help',
    requiredText: ['What is wrong?', 'Pick the next step'],
  },
  {
    id: 'contact',
    route: '/contact',
    screenshotPrefix: 'contact',
      requiredText: ['Contact', 'Chummer5 Discord', 'Open Discord'],
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
    const hero = page.locator('[data-homepage-section="hero"]');
    const footer = page.locator('.site-footer');
    const navLinks = page.locator('.site-nav a, .site-nav__current');

    await expect(heroTitle).toContainText('Chummer');
    await expect(primaryCta).toHaveAttribute('aria-label', 'Download Chummer');
    await expect(page.locator('.minimal-meta')).toContainText('Current public installer');
    await expect(page.locator('[data-homepage-section="workflow"]')).toHaveCount(0);
    await expect(page.locator('[data-homepage-section="downloads"]')).toHaveCount(0);
    await expect(page.locator('.minimal-inline-links')).toContainText('Help');
    await expect(page.locator('.minimal-inline-links')).not.toContainText('Participate');
    await expect(page.locator('.minimal-inline-links')).not.toContainText('Status');
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
    const heroSectionBox = await hero.boundingBox();
    if (!heroBox || !ctaBox) {
      failures.push(`${viewport.width}x${viewport.height}: hero title or primary CTA is not visible`);
    }
    if (viewport.width >= 1024 && (!heroSectionBox || heroSectionBox.y + heroSectionBox.height > viewport.height)) {
      failures.push(`${viewport.width}x${viewport.height}: hero still exceeds the first viewport`);
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
      hero_first_viewport_fit: !heroSectionBox ? false : heroSectionBox.y + heroSectionBox.height <= viewport.height,
      footer_visible: await footer.isVisible(),
      inline_nav_visible: await page.locator('.site-nav').isVisible(),
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
