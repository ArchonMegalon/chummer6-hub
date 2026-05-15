import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const ledgerViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Ledger.cshtml');

test('black ledger dispatch route family is implemented', async () => {
  const controller = readFileSync(controllerPath, 'utf8');
  const ledgerView = readFileSync(ledgerViewPath, 'utf8');

  expect(controller).toContain('[HttpGet("/ledger/dispatches")]');
  expect(controller).toContain('[HttpGet("/ledger/dispatches/{dispatchId}")]');
  expect(controller).toContain('[HttpGet("/ledger/turns/{turn}/dispatches")]');
  expect(controller).toContain('[HttpGet("/ledger/factions/{factionId}/dispatches")]');
  expect(ledgerView).toContain('Latest dispatches');
  expect(ledgerView).toContain('Receipt-backed narrative, not free-floating lore.');
  expect(ledgerView).toContain('Dispatch detail');
});
