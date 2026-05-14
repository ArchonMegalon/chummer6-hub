import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const ledgerViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Ledger.cshtml');
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('black ledger hub routes and CTA are first-party', async () => {
  const controller = readFileSync(controllerPath, 'utf8');
  const ledgerView = readFileSync(ledgerViewPath, 'utf8');
  const landingView = readFileSync(landingViewPath, 'utf8');

  expect(controller).toContain('[HttpGet("/ledger")]');
  expect(controller).toContain('[HttpGet("/black-ledger")]');
  expect(controller).toContain('[HttpGet("/ledger/stats")]');
  expect(controller).toContain('[HttpGet("/ledger/factions")]');
  expect(controller).toContain('[HttpGet("/ledger/packages")]');
  expect(controller).toContain('[HttpGet("/ledger/closeouts")]');
  expect(landingView).toContain('var ledgerHref = "/ledger";');
  expect(ledgerView).toContain('Opt-in aggregate only');
  expect(ledgerView).toContain('This page explains pressure, not people.');
});
