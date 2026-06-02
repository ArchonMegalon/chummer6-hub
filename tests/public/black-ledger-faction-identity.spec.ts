import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const factions = [
  { name: 'Glass Tower Compact', slug: 'glass-tower-compact' },
  { name: 'Rust Market Syndicate', slug: 'rust-market-syndicate' },
  { name: 'Ashline Circle', slug: 'ashline-circle' },
  { name: 'Neon Docks Union', slug: 'neon-docks-union' },
  { name: 'Ghostline Network', slug: 'ghostline-network' },
  { name: 'Barrens Free Wardens', slug: 'barrens-free-wardens' },
];

test('faction pages carry logos, backdrops, ledgers, and one clear public CTA', async ({ page }) => {
  const visited: Array<Record<string, unknown>> = [];
  await page.goto(`${baseUrl}/ledger/factions`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.faction-profile-card')).toHaveCount(6);

  for (const faction of factions) {
    await page.goto(`${baseUrl}/ledger/factions/${faction.slug}`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#ledger-faction-file')).toContainText(faction.name);
    await expect(page.locator('.faction-detail-hero__logo')).toBeVisible();
    await expect(page.locator('.score-ledger-grid .route-choice-card')).toHaveCount(4);
    visited.push({
      route: `/ledger/factions/${faction.slug}`,
      logo_count: await page.locator('.faction-detail-hero__logo').count(),
      ledger_count: await page.locator('.score-ledger-grid .route-choice-card').count(),
    });
  }

  writeJsonArtifact('BLACK_LEDGER_GLOBE_CANON.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    faction_routes: visited,
  });
});
