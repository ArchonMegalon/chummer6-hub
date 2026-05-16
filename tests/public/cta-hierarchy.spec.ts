import { expect, test } from 'playwright/test';
import { writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = 'https://chummer.run';

test('homepage keeps the intended compact CTA hierarchy on desktop and mobile', async ({ browser }) => {
  test.setTimeout(120000);
  const viewports = [
    { name: 'desktop', width: 1366, height: 768 },
    { name: 'mobile', width: 390, height: 844 },
  ];
  const results: Array<Record<string, unknown>> = [];
  const failures: string[] = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ baseURL: baseUrl, viewport });
    await page.goto(baseUrl, { waitUntil: 'networkidle' });

    const heroActions = page.locator('.launch-hero__actions a.button-like');
    const texts = await heroActions.allTextContents();
    const normalized = texts.map((text) => text.replace(/\s+/g, ' ').trim());
    const expected = ['Enter Black Ledger', 'Download Chummer'];
    expect(normalized.slice(0, 2), `${viewport.name} hero CTA order`).toEqual(expected);

    const heroBoxes = [];
    for (let index = 0; index < Math.min(await heroActions.count(), 2); index += 1) {
      heroBoxes.push(await heroActions.nth(index).boundingBox());
    }

    const accountSection = page.locator('[data-homepage-section="play-downloads"]');
    const accountPrimary = accountSection.locator('.editorial-strip__action').first();
    const accountPrimaryTop = (await accountPrimary.boundingBox())?.y ?? 0;
    const heroPrimaryTop = heroBoxes[0]?.y ?? 0;
    if (accountPrimaryTop <= heroPrimaryTop) {
      failures.push(`${viewport.name}: account CTA surfaced above hero CTA`);
    }

    results.push({
      viewport: viewport.name,
      hero_ctas: normalized.slice(0, 2),
      hero_boxes: heroBoxes,
      account_primary_top: accountPrimaryTop,
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
      '- Hero keeps two ranked CTAs: `Enter Black Ledger` and `Download Chummer`.',
      '- Homepage now stays on the five-section model: hero, score-strip, factions, play-downloads, footer.',
      '- Globe, score chips, and faction identity own the front door instead of proof panels.',
      '- Play shell and status remain lower on the page instead of competing with the globe hero.',
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
