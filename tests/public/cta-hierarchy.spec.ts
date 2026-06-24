import { expect, test } from 'playwright/test';
import { writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('homepage keeps the intended live CTA hierarchy on desktop and mobile', async ({ browser }) => {
  test.setTimeout(120000);
  const viewports = [
    { name: 'desktop', width: 1366, height: 768 },
    { name: 'mobile', width: 390, height: 844 },
  ];
  const results: Array<Record<string, unknown>> = [];
  const failures: string[] = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

    const heroActions = page.locator('.minimal-hero .minimal-actions a.button-like');

    const texts = await heroActions.allTextContents();
    const normalized = texts.map((text) => text.replace(/\s+/g, ' ').trim());
    const expected = ['Download Chummer'];
    expect(normalized, `${viewport.name} hero CTA order`).toEqual(expected);

    const heroBoxes = [];
    for (let index = 0; index < await heroActions.count(); index += 1) {
      heroBoxes.push(await heroActions.nth(index).boundingBox());
    }

    await expect(page.locator('[data-homepage-section="help"]')).toHaveCount(0);
    const nonHeroPrimaryCtas = await page.locator('main .button-like--primary').evaluateAll((items) =>
      items
        .filter((item) => !item.closest('.minimal-hero'))
        .map((item) => (item.textContent || '').replace(/\s+/g, ' ').trim())
        .filter(Boolean),
    );
    if (nonHeroPrimaryCtas.length > 0) {
      failures.push(`${viewport.name}: found competing primary CTA(s) outside the hero: ${nonHeroPrimaryCtas.join(', ')}`);
    }
    await expect(page.locator('.site-nav')).toHaveCount(0);
    await expect(page.locator('[data-nav-toggle]')).toHaveCount(0);

    results.push({
      viewport: viewport.name,
      hero_ctas: normalized,
      hero_boxes: heroBoxes,
      competing_primary_ctas: nonHeroPrimaryCtas,
      inline_nav_visible: false,
    });

    await page.close();
  }

  writeJsonArtifact('CTA_HIERARCHY.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    failures,
    results,
  });

  writeMarkdownArtifact(
    'HOMEPAGE_SIMPLIFICATION_CHANGELOG.md',
    [
      '# Homepage Simplification Changelog',
      '',
      '- Hero keeps one primary CTA: `Download Chummer`.',
      '- Homepage remains compact: one hero and no repeated support block or download strip.',
      '- Release posture stays off the first screen and lives on Status instead.',
      '- Support paths stay inline in the hero instead of competing as a second CTA block.',
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
