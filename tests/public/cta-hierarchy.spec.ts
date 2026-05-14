import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const manifestPath = path.join(repoRoot, '.codex-design', 'product', 'PUBLIC_LANDING_MANIFEST.yaml');
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('homepage keeps the intended CTA hierarchy and six-section model', async () => {
  const manifest = readFileSync(manifestPath, 'utf8');
  const landing = readFileSync(landingViewPath, 'utf8');

  expect(manifest).toContain('- label: Open downloads');
  expect(landing).toContain('Open downloads');
  expect(landing).toContain('@enterHubLabel');
  expect(landing).toContain('Explore Karma Forge');

  const primaryIndex = landing.indexOf('Open downloads');
  const hubIndex = landing.indexOf('@enterHubLabel');
  const forgeIndex = landing.indexOf('Explore Karma Forge');
  expect(primaryIndex).toBeGreaterThan(-1);
  expect(hubIndex).toBeGreaterThan(primaryIndex);
  expect(forgeIndex).toBeGreaterThan(hubIndex);

  expect(landing).toContain('data-homepage-section="hero"');
  expect(landing).toContain('data-homepage-section="choose-your-path"');
  expect(landing).toContain('data-homepage-section="what-works-today"');
  expect(landing).toContain('data-homepage-section="preview"');
  expect(landing).toContain('data-homepage-section="account-value"');
  expect(landing).toContain('data-homepage-section="trust-footer"');

  const sectionCount = (landing.match(/data-homepage-section=/g) ?? []).length;
  expect(sectionCount).toBe(6);
});
