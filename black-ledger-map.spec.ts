import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');
const ledgerViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Ledger.cshtml');
const cssPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'css', 'site.css');

test('black ledger map is SVG-first, keyboard reachable, and not a blurry bitmap fallback', async () => {
  const landingView = readFileSync(landingViewPath, 'utf8');
  const ledgerView = readFileSync(ledgerViewPath, 'utf8');
  const css = readFileSync(cssPath, 'utf8');

  expect(landingView).toContain('svg viewBox="0 0 1200 760"');
  expect(ledgerView).toContain('svg viewBox="0 0 1200 760"');
  expect(landingView).toContain('tabindex="0"');
  expect(ledgerView).toContain('tabindex="0"');
  expect(landingView).toContain('ledger-world-panel__legend');
  expect(ledgerView).toContain('id="district-');
  expect(css).toContain('.ledger-world-panel__district:hover');
  expect(css).toContain('.ledger-world-shell__district:focus');
  expect(landingView).not.toMatch(/\.png|\.jpg|\.jpeg|background-image/i);
  expect(ledgerView).not.toMatch(/\.png|\.jpg|\.jpeg|background-image/i);
});
