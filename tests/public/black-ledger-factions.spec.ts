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

test('black ledger faction index and dedicated pages exist for the seeded six', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/factions`, { waitUntil: 'domcontentloaded' });

  for (const faction of factions) {
    await expect(page.locator(`[data-faction-card="${faction.slug}"] [data-faction-file-link="${faction.slug}"]`)).toHaveCount(1);
    await expect(page.locator('#ledger-factions')).toContainText(faction.name);
  }

  const visited: string[] = [];
  for (const faction of factions) {
    await page.goto(`${baseUrl}/ledger/factions/${faction.slug}`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#ledger-faction-file')).toContainText(faction.name);
    await expect(page.locator('#ledger-faction-file')).toContainText('Package pressure');
    await expect(page.locator('#ledger-faction-file')).toContainText('Safety: public');
    await expect(page.locator('#ledger-faction-file')).toContainText('Video: Chummer motion');
    visited.push(`/ledger/factions/${faction.slug}`);
  }

  writeJsonArtifact('BLACK_LEDGER_FACTION_PAGES.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    faction_count: factions.length,
    visited_routes: visited,
  });
});
