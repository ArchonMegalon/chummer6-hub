import { expect, test } from 'playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const repoRoot = process.cwd();
const builderView = readFileSync(path.join(repoRoot, 'Chummer.Run.Api/Views/PublicLanding/LedgerFactionCreate.cshtml'), 'utf8');

test('black ledger faction builder stays interactive and visible in source while guest-gated live', async ({ page }) => {
  const response = await page.goto(`${baseUrl}/account/ledger/factions/create?charterType=challenger`, { waitUntil: 'networkidle' });
  expect(response?.status()).toBe(200);
  expect(page.url()).toContain('/login?next=');

  for (const token of [
    'input type="text"',
    'input type="radio"',
    'select name="startingDistrictId"',
    'select name="rivalFactionId"',
    'input type="checkbox"',
    'challenger factions start weaker',
  ]) {
    expect(builderView).toContain(token);
  }

  writeJsonArtifact('BLACK_LEDGER_FACTION_CHARTER_BUILDER.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/account/ledger/factions/create?charterType=challenger',
    guest_redirects_to_login: true,
    visible_builder_controls_present: true,
  });
});
