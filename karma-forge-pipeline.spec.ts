import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const servicePath = path.join(repoRoot, 'Chummer.Run.Api', 'Services', 'Community', 'BlackLedgerPublicStatsService.cs');

test('landing keeps the Karma Forge pipeline governed and route-backed', async () => {
  const controller = readFileSync(controllerPath, 'utf8');
  const service = readFileSync(servicePath, 'utf8');

  expect(controller).toContain('[HttpGet("/participate/karma-forge")]');
  expect(controller).toContain('[HttpPost("/participate/karma-forge")]');
  expect(controller).toContain('/participate/karma-forge/submitted/{submissionId}');
  expect(service).toContain('Karma Forge Candidate Feed');
  expect(service).toContain('Discovery-linked');
  expect(service).toContain('Discovery packets can point at candidate motion, but not shipped status, until release proof is real.');
  expect(service).toContain('/ledger/packages');
  expect(service).toContain('/karma-forge');
});
