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
  expect(view).toContain('Downloads first. Hub second. Ledger and Forge when you need context.');

  expect(view).toContain('Choose your path');
  expect(view).toContain('Id = "build"');
  expect(view).toContain('Id = "hub"');
  expect(view).toContain('Id = "forge"');
  expect(view).toContain('Id = "ledger"');

  expect(view).toContain('What works today');
  expect(view).toContain('Black Ledger command deck');
  expect(view).toContain('Turn 1 already ran. The city is moving.');
  expect(view).toContain('Account value');
});
