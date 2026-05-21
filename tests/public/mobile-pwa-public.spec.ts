import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const mobileViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'MobileProjection.cshtml');
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const manifestPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'manifest.json');
const manifestAliasPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'manifest.webmanifest');
const swPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'service-worker.js');

test('mobile and PWA public routes keep installability and role entry explicit', async () => {
  const mobileView = readFileSync(mobileViewPath, 'utf8');
  const controller = readFileSync(controllerPath, 'utf8');
  const manifest = readFileSync(manifestPath, 'utf8');
  const manifestAlias = readFileSync(manifestAliasPath, 'utf8');
  const serviceWorker = readFileSync(swPath, 'utf8');

  expect(mobileView).toContain('Install this app');
  expect(mobileView).toContain('beforeinstallprompt');
  expect(mobileView).toContain('One bounded shell, five explicit promises.');
  expect(mobileView).toContain('Player, GM, and observer routes converge on one shell.');
  expect(mobileView).toContain('_SignedInTrustStatusPanel');
  expect(mobileView).toContain('_PublicTrustPulsePanel');
  expect(mobileView).toContain('/manifest.webmanifest');

  expect(controller).toContain('[HttpGet("/mobile")]');
  expect(controller).toContain('[HttpGet("/pwa")]');
  expect(controller).toContain('[HttpGet("/play")]');
  expect(controller).toContain('[HttpGet("/player")]');
  expect(controller).toContain('[HttpGet("/gm")]');
  expect(controller).toContain('[HttpGet("/observer")]');

  expect(manifest).toContain('"id": "/mobile"');
  expect(manifest).toContain('"display_override"');
  expect(manifest).toContain('"screenshots"');
  expect(manifest).toContain('"start_url": "/mobile"');
  expect(manifest).toContain('"url": "/play"');
  expect(manifest).toContain('"url": "/play/continuity"');
  expect(manifestAlias).toContain('"start_url": "/mobile"');
  expect(manifestAlias).toContain('"shortcuts"');
  expect(serviceWorker).toContain('"/mobile"');
  expect(serviceWorker).toContain('"/play"');
  expect(serviceWorker).toContain('"/play/continuity"');
  expect(serviceWorker).toContain('"/manifest.webmanifest"');
  expect(serviceWorker).toContain('navigationPreload');
});
