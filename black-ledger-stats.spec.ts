import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');
const servicePath = path.join(repoRoot, 'Chummer.Run.Api', 'Services', 'Community', 'BlackLedgerPublicStatsService.cs');

test('landing exposes public-safe Black Ledger stats language', async () => {
  const view = readFileSync(landingViewPath, 'utf8');
  const service = readFileSync(servicePath, 'utf8');

  expect(view).toContain('Model.BlackLedgerStats');
  expect(view).not.toContain('Barrens adepts 34%');
  expect(view).not.toContain('128,400Y active favors');
  expect(service).toContain('Fictional runner/campaign statistics only');
  expect(service).toContain('Opt-in aggregate only');
  expect(service).toContain('MysAd density');
  expect(service).toContain('Debt Heat');
  expect(service).toContain('Package pressure');
  expect(service).toContain('Chaos index');
  expect(service).toContain('Scope: "Public aggregate"');
  expect(service).toContain('SampleSize:');
  expect(service).toContain('PrivacyNote:');

  expect(service).not.toContain('drug addicts');
  expect(service).not.toContain('dumbest');
  expect(service).not.toContain('ugliest');
});
