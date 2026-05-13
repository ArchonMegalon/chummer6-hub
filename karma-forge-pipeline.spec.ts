import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('landing keeps the Karma Forge pipeline governed and route-backed', async () => {
  const view = readFileSync(landingViewPath, 'utf8');

  expect(view).toContain('Karma Forge pipeline');
  expect(view).toContain('Signal');
  expect(view).toContain('Compatibility');
  expect(view).toContain('Design decision');
  expect(view).toContain('Package candidate');
  expect(view).toContain('Test gate');
  expect(view).toContain('Release proof');
  expect(view).toContain('Closeout');
  expect(view).toContain('href="@forgeHref"');
  expect(view).toContain('href="@packagesHref"');
});
