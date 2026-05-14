import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const viewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Anarchy.cshtml');
const servicePath = path.join(repoRoot, 'Chummer.Run.Api', 'Services', 'Community', 'AnarchyPreviewService.cs');

test('anarchy preview route family is implemented', async () => {
  const controller = readFileSync(controllerPath, 'utf8');
  const view = readFileSync(viewPath, 'utf8');
  const service = readFileSync(servicePath, 'utf8');

  expect(controller).toContain('[HttpGet("/anarchy")]');
  expect(controller).toContain('[HttpGet("/play/anarchy")]');
  expect(controller).toContain('[HttpGet("/ledger/anarchy")]');
  expect(view).toContain('Not an SR5 skin. Not an SR6 mode.');
  expect(view).toContain('Portable runner packet');
  expect(service).toContain('shadowrun_anarchy');
  expect(service).toContain('Playable preview');
});
