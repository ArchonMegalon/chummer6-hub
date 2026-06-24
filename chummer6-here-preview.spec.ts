import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('homepage browser preview pitch stays clearly separate from the real desktop ui', async () => {
  const view = readFileSync(landingViewPath, 'utf8');

  expect(view).toContain('Preview test');
  expect(view).toContain('Chummer6 here');
  expect(view).toContain('different UI from the real Chummer6 desktop app');
  expect(view).toContain('functionality preview rather than the main shipped workbench');
  expect(view).toContain('Use the desktop build');
  expect(view).toContain('Track preview status');
  expect(view).toContain('data-homepage-preview="chummer6-here"');
});
