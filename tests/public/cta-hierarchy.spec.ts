import { expect, test } from 'playwright/test';
import { writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = 'https://chummer.run';

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
    await page.goto(baseUrl, { waitUntil: 'networkidle' });

    const heroActions = page.locator('.launch-hero__actions a.button-like');
    const texts = await heroActions.allTextContents();
    const normalized = texts.map((text) => text.replace(/\s+/g, ' ').trim());
    const expected = ['Open downloads', 'Enter the hub', 'Explore Karma Forge'];
    expect(normalized.slice(0, 3), `${viewport.name} hero CTA order`).toEqual(expected);

    const heroBoxes = [];
    for (let index = 0; index < Math.min(await heroActions.count(), 3); index += 1) {
      heroBoxes.push(await heroActions.nth(index).boundingBox());
    }

    const accountSection = page.locator('[data-homepage-section="account-value"]');
    const accountPrimary = accountSection.locator('.button-like--primary');
    const accountPrimaryTop = (await accountPrimary.boundingBox())?.y ?? 0;
    const heroPrimaryTop = heroBoxes[0]?.y ?? 0;
    if (accountPrimaryTop <= heroPrimaryTop) {
      failures.push(`${viewport.name}: account CTA surfaced above hero CTA`);
    }

    results.push({
      viewport: viewport.name,
      hero_ctas: normalized.slice(0, 3),
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
      '- Hero keeps three ranked CTAs: `Open downloads`, `Enter the hub`, `Explore Karma Forge`.',
      '- Homepage remains on the six-section model: hero, choose-your-path, what-works-today, preview, account-value, trust-footer.',
      '- Black Ledger and Karma Forge stay in the preview lane instead of overwhelming the hero with extra proof panels.',
      '- Account CTAs remain lower on the page instead of competing with the install-first hero path.',
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
