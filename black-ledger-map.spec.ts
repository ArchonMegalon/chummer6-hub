import { readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');
const ledgerViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Ledger.cshtml');
const cssPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'css', 'site.css');
const geoscapeScriptPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'js', 'black-ledger-geoscape.js');
const globeMediaRoot = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'media', 'ledger', 'globe');

test('black ledger globe is canvas-first, keyboard reachable, and not the legacy inline SVG map', async () => {
  const landingView = readFileSync(landingViewPath, 'utf8');
  const ledgerView = readFileSync(ledgerViewPath, 'utf8');
  const css = readFileSync(cssPath, 'utf8');
  const geoscapeScript = readFileSync(geoscapeScriptPath, 'utf8');

  expect(landingView).toContain('data-black-ledger-geoscape-root');
  expect(ledgerView).toContain('data-black-ledger-geoscape-root');
  expect(landingView).toContain('black-ledger-geoscape.js');
  expect(ledgerView).toContain('black-ledger-geoscape.js');
  expect(`${landingView}\n${ledgerView}`).not.toContain('svg viewBox="0 0 1200 760"');
  expect(ledgerView).toContain('districtAnchorId = id => $"district-{id}"');
  expect(ledgerView).toContain('data-map-district-card');
  expect(geoscapeScript).toContain('canvas class="black-ledger-geoscape__canvas"');
  expect(geoscapeScript).toContain('canvas class="black-ledger-geoscape__webgl"');
  expect(geoscapeScript).toContain('black-ledger-geoscape__fallback-list');
  expect(geoscapeScript).toContain('data-faction-select');
  expect(geoscapeScript).toContain('renderWebGlBase(time, width, height, radius)');
  expect(geoscapeScript).not.toContain('usedVideoGlobe ? false : this.renderWebGlBase');
  expect(css).toContain('.black-ledger-geoscape__video-plate');
  expect(css).not.toContain('data-video-globe="ready"] .black-ledger-geoscape__webgl {\n  opacity: 0;');

  const mp4 = statSync(path.join(globeMediaRoot, 'black-ledger-video-globe-idle.mp4'));
  const webm = statSync(path.join(globeMediaRoot, 'black-ledger-video-globe-idle.webm'));
  const poster = statSync(path.join(globeMediaRoot, 'black-ledger-video-globe-idle-poster.png'));
  expect(mp4.size).toBeGreaterThan(500_000);
  expect(webm.size).toBeGreaterThan(300_000);
  expect(poster.size).toBeGreaterThan(50_000);
});
