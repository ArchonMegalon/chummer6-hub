import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');
const servicePath = path.join(repoRoot, 'Chummer.Run.Api', 'Services', 'Community', 'BlackLedgerPublicStatsService.cs');

test('karma forge alias exists and ledger linkage stays first-party', async () => {
  const controller = readFileSync(controllerPath, 'utf8');
  const landingView = readFileSync(landingViewPath, 'utf8');
  const service = readFileSync(servicePath, 'utf8');

  expect(controller).toContain('[HttpGet("/karma-forge")]');
  expect(controller).toContain('=> Redirect("/participate/karma-forge")');
  expect(landingView).toContain('Open Black Ledger');
  expect(landingView).toContain('Download Chummer');
  expect(service).toContain('/karma-forge');
  expect(service).toContain('/ledger/packages');
});
