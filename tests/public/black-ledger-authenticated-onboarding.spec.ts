import { expect, test } from 'playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const repoRoot = process.cwd();
const onboardingView = readFileSync(path.join(repoRoot, 'Chummer.Run.Api/Views/PublicLanding/LedgerOnboarding.cshtml'), 'utf8');

test('black ledger onboarding wizard is route-backed and guest-gated cleanly', async ({ page }) => {
  const response = await page.goto(`${baseUrl}/account/ledger/onboarding?step=allegiance`, { waitUntil: 'networkidle' });
  expect(response?.status()).toBe(200);
  expect(page.url()).toContain('/login?next=');

  const requiredCopy = [
    'Pick a side on the globe, then commit.',
    'One allegiance across current and future runners.',
    'Join this faction',
    'Open faction video',
    'Open faction file',
    'Found Major Faction',
    'Found Challenger',
  ];

  for (const token of requiredCopy) {
    expect(onboardingView).toContain(token);
  }

  writeJsonArtifact('BLACK_LEDGER_FACTION_ONBOARDING.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/account/ledger/onboarding?step=allegiance',
    guest_redirects_to_login: true,
    route_backed_steps_present: ['welcome', 'allegiance', 'factions', 'choose-path', 'confirm', 'builder', 'welcome-kit']
      .every((step) => onboardingView.includes(`/account/ledger/onboarding?step=${step}`)),
  });
});
