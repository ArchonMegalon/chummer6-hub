import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('landing exposes public-safe Black Ledger stats language', async () => {
  const view = readFileSync(landingViewPath, 'utf8');

  expect(view).toContain('fictional runner/campaign statistics only');
  expect(view).toContain('Opt-in aggregate only');
  expect(view).toContain('MysAd density');
  expect(view).toContain('Debt Heat');
  expect(view).toContain('Package pressure');
  expect(view).toContain('Chaos index');

  expect(view).not.toContain('drug addicts');
  expect(view).not.toContain('dumbest');
  expect(view).not.toContain('ugliest');
});
