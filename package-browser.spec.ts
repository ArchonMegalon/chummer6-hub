import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const packagesViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Packages.cshtml');
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const featureRegistryPath = path.join(repoRoot, '.codex-design', 'product', 'PUBLIC_FEATURE_REGISTRY.yaml');

test('package browser keeps product-quality proof and route ownership explicit', async () => {
  const view = readFileSync(packagesViewPath, 'utf8');
  const controller = readFileSync(controllerPath, 'utf8');
  const registry = readFileSync(featureRegistryPath, 'utf8');

  expect(view).toContain('Package class model');
  expect(view).toContain('Compatibility:');
  expect(view).toContain('Governance:');
  expect(view).toContain('Evidence:');
  expect(view).toContain('Votes and follows emit first-party receipts.');
  expect(view).toContain('Use Downloads for builds, Packages for class and compatibility, and Help when the issue turns private.');

  expect(controller).toContain('[HttpGet("/packages")]');
  expect(controller).toContain('[HttpGet("/packages/{packageId}")]');
  expect(controller).toContain('[HttpGet("/packages/{packageId}/vote")]');
  expect(controller).toContain('[HttpGet("/packages/{packageId}/follow")]');

  expect(registry).toContain('href: /packages');
  expect(registry).toContain('title: Package browser');
});
