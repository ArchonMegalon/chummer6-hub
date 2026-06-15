import { expect, test } from 'playwright/test';
import { writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('homepage stays within the pre-gold noise budget', async ({ page }) => {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  const sections = page.locator('[data-homepage-section]');
  await expect(sections).toHaveCount(5);

  const navLabels = await page.locator('[aria-label="Primary navigation"] a, [aria-label="Primary navigation"] .site-sidebar__current').evaluateAll((items) =>
    items.map((item) => (item.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean),
  );
  expect(navLabels).toEqual(['Home', 'Get Chummer', 'Ledger', 'Help']);

  const hero = page.locator('[data-homepage-section="hero"]');
  const heroText = (await hero.textContent()) || '';
  expect(heroText.toLowerCase()).not.toContain('proof');
  expect(heroText.toLowerCase()).not.toContain('artifact');
  expect(heroText.toLowerCase()).not.toContain('repo');

  writeMarkdownArtifact(
    'FINAL_PUBLIC_UX_REDESIGN_VERDICT.md',
    [
      '# Final public UX redesign verdict',
      '',
      '- Homepage sections: `5`',
      '- Primary nav: `Home, Get Chummer, Ledger, Help`',
      '- First-screen proof noise: `0`',
      '- Verdict: `READY`',
    ].join('\n'),
  );
});
