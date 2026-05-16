import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('landing keeps the Karma Forge pipeline governed and route-backed', async () => {
  const view = readFileSync(landingViewPath, 'utf8');

  expect(view).toContain('Karma Forge');
  expect(view).toContain('Governed preview');
  expect(view).toContain('Signal intake');
  expect(view).toContain('Package candidates');
  expect(view).toContain('Closeout proof');
  expect(view).toContain('rules pain, package demand, or a change request that needs evidence instead of chat noise');
  expect(view).toContain('href="@forgeHref"');
});
