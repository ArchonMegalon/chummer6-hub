import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('landing implements the flagship Black Ledger Gate structure', async () => {
  const view = readFileSync(landingViewPath, 'utf8');

  expect(view).toContain('Build the runner. Run the table. Keep the ledger honest.');
  expect(view).toContain('Explainable Shadowrun campaign OS');
  expect(view).toContain('Open downloads');
  expect(view).toContain('Enter the hub');
  expect(view).toContain('Explore Karma Forge');

  expect(view).toContain('Five gateways');
  expect(view).toContain('Id = "build"');
  expect(view).toContain('Id = "play"');
  expect(view).toContain('Id = "packages"');
  expect(view).toContain('Id = "forge"');
  expect(view).toContain('Id = "ledger"');

  expect(view).toContain('Black Ledger world panel');
  expect(view).toContain('What is real today');
  expect(view).toContain('Participation / Fixer Rep preview');
});
