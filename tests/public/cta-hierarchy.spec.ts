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

    const heroActions = page.locator('.launch-hero__actions a.button-like');
    const heroClass = (await page.locator('.launch-hero').first().getAttribute('class')) ?? '';
    expect(heroClass, `${viewport.name} hero posture class`).toContain('launch-hero--ledger');
    expect(heroClass, `${viewport.name} retired hero posture class`).not.toContain('launch-hero--pregold');

    const texts = await heroActions.allTextContents();
    const normalized = texts.map((text) => text.replace(/\s+/g, ' ').trim());
    const expected = ['Open Black Ledger', 'Download Chummer'];
    expect(normalized.slice(0, 2), `${viewport.name} hero CTA order`).toEqual(expected);

    const heroBoxes = [];
    for (let index = 0; index < Math.min(await heroActions.count(), 2); index += 1) {
      heroBoxes.push(await heroActions.nth(index).boundingBox());
    }

    const supportSection = page.locator('[data-public-section="footer"]');
    const supportPrimary = supportSection.locator('.button-like--primary');
    const supportPrimaryTop = (await supportPrimary.boundingBox())?.y ?? 0;
    const heroPrimaryTop = heroBoxes[0]?.y ?? 0;
    if (supportPrimaryTop <= heroPrimaryTop) {
      failures.push(`${viewport.name}: support CTA surfaced above hero CTA`);
    }
    const navPanelOpen = await page.evaluate(() => document.body.classList.contains('nav-panel-open'));
    if (navPanelOpen) {
      failures.push(`${viewport.name}: navigation panel is open on first paint`);
    }

    results.push({
      viewport: viewport.name,
      hero_class: heroClass,
      hero_ctas: normalized.slice(0, 2),
      hero_boxes: heroBoxes,
      support_primary_top: supportPrimaryTop,
      nav_panel_open: navPanelOpen,
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
      '- Hero keeps two ranked CTAs: `Open Black Ledger`, `Download Chummer`.',
      '- Homepage remains on the five-section model: hero, score-strip, factions, flagship-promo, play-downloads.',
      '- Release posture stays off the first screen and lives on Status instead.',
      '- Support/help CTAs remain lower on the page instead of competing with the hero path.',
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
