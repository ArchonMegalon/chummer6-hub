import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const mobileViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'MobileProjection.cshtml');
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const manifestPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'manifest.json');
const swPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'service-worker.js');

test('mobile and PWA public routes keep installability and role entry explicit', async () => {
  const mobileView = readFileSync(mobileViewPath, 'utf8');
  const controller = readFileSync(controllerPath, 'utf8');
  const manifest = readFileSync(manifestPath, 'utf8');
  const serviceWorker = readFileSync(swPath, 'utf8');

  expect(mobileView).toContain('Mobile play shell preview; installability proof pending.');
  expect(mobileView).toContain('Manifest and service worker live');
  expect(mobileView).toContain('Player, GM, and observer routes converge on one shell.');

  expect(controller).toContain('[HttpGet("/mobile")]');
  expect(controller).toContain('[HttpGet("/pwa")]');
  expect(controller).toContain('[HttpGet("/play")]');
  expect(controller).toContain('[HttpGet("/player")]');
  expect(controller).toContain('[HttpGet("/gm")]');
  expect(controller).toContain('[HttpGet("/observer")]');

  expect(manifest).toContain('"start_url": "/mobile"');
  expect(manifest).toContain('"url": "/play"');
  expect(serviceWorker).toContain('"/mobile"');
  expect(serviceWorker).toContain('"/play"');
});
