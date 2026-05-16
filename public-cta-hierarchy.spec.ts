import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const manifestPath = path.join(repoRoot, '.codex-design', 'product', 'PUBLIC_LANDING_MANIFEST.yaml');
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');
const downloadsViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Downloads.cshtml');

test('public CTA hierarchy keeps downloads primary and account install contextual', async () => {
  const manifest = readFileSync(manifestPath, 'utf8');
  const landing = readFileSync(landingViewPath, 'utf8');
  const downloads = readFileSync(downloadsViewPath, 'utf8');

  expect(manifest).toContain('- label: Open downloads');
  expect(manifest).toContain('account_aware_install_cta_label: Create account to install');
  expect(manifest).toContain('product_proof_primary_label: Open downloads');

  expect(landing).toContain('Open downloads');
  expect(landing).toContain('Recommended path');
  expect(landing).toContain('Account-aware install handoff');
  expect(landing).toContain('Current preview install');
  expect(landing).toContain('Already have an account? Sign in');
  expect(landing).toContain('Downloads first. Hub second. Ledger and Forge when you need context.');

  expect(downloads).toContain('Open downloads first. Create account for guided install only when you want first-launch recovery, linked restore, and support follow-through to stay attached.');
  expect(downloads).not.toContain('Create account to install</a>');
});
