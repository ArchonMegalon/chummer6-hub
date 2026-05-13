import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');
const mobileViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'MobileProjection.cshtml');
const packagesViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Packages.cshtml');

test('public mobile-facing surfaces keep route-owned sections that can collapse responsively', async () => {
  const landing = readFileSync(landingViewPath, 'utf8');
  const mobile = readFileSync(mobileViewPath, 'utf8');
  const packages = readFileSync(packagesViewPath, 'utf8');

  expect(landing).toContain('launch-hero__shell');
  expect(landing).toContain('workflow-grid');
  expect(landing).toContain('route-choice-grid');

  expect(mobile).toContain('continuity-band');
  expect(mobile).toContain('route-choice-grid');
  expect(mobile).toContain('compact-rail');

  expect(packages).toContain('route-choice-grid');
  expect(packages).toContain('compact-rail');
});
