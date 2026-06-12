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
  expect(manifest).toContain('- label: Create account');
  expect(manifest).toContain('product_proof_primary_label: Open downloads');

  expect(landing).toContain('Open downloads');
  expect(landing).toContain('Open Black Ledger');
  expect(landing).toContain('Download Chummer');
  expect(landing).toContain('Open play shell');
  expect(landing).toContain('Open status');
  expect(landing).toContain('Ledger for the city. Downloads for the build. Play for the shell. Status for release health.');

  expect(downloads).toContain('Open downloads');
  expect(downloads).not.toContain('Create account to install</a>');
});
