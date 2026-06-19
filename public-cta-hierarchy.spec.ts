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

  expect(manifest).toContain('- label: Download Chummer');
  expect(manifest).toContain('- label: Create account');
  expect(manifest).toContain('product_proof_primary_label: Download Chummer');

  expect(landing).toContain('Stable</a>');
  expect(landing).toContain('Nightly</a>');
  expect(landing).toContain('Get the app');
  expect(landing).toContain('Need help?');
  expect(landing).not.toContain('Open Black Ledger');

  expect(downloads).toContain('Nightly');
  expect(downloads).toContain('Stable');
  expect(downloads).toContain('data-release-lane="nightly"');
  expect(downloads).toContain('data-release-lane="stable"');
  expect(downloads).toContain('Choose Stable or Nightly. Windows and Linux installers are published here.');
  expect(downloads).not.toContain('Create account to install</a>');
});
