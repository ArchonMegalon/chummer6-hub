import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const accountViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'Accounts', 'Account.cshtml');
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'AccountsController.cs');
const manifestPath = path.join(repoRoot, '.codex-design', 'product', 'PUBLIC_LANDING_MANIFEST.yaml');

test('account participation dashboard stays dedicated and opt-in', async () => {
  const accountView = readFileSync(accountViewPath, 'utf8');

  expect(accountView).toContain('Participation dashboard');
  expect(accountView).toContain('Contribution cred');
  expect(accountView).toContain('Impact closeout notifications');
  expect(accountView).toContain('publicContributionProfileOptIn');
  expect(accountView).toContain('impactCloseoutNotifications');
  expect(accountView).toContain('Impact journal');
  expect(accountView).toContain('Public recognition stays off unless you opt in.');
  expect(accountView).toContain('Votes show demand; Chummer-owned proof decides what ships.');
  expect(accountView).not.toContain('Earn Karma');
  expect(accountView).not.toContain('Top voters decide roadmap');
});

test('account participation route stays published in controller and canon', async () => {
  const controller = readFileSync(controllerPath, 'utf8');
  const manifest = readFileSync(manifestPath, 'utf8');

  expect(controller).toContain('/account/participation');
  expect(manifest).toContain('/account/participation');
  expect(manifest).toContain('purpose: signed_in_participation');
});
