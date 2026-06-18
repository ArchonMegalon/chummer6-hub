import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('landing implements the product-first homepage structure', async () => {
  const view = readFileSync(landingViewPath, 'utf8');

  expect(view).toContain('Build the runner. Run the night.');
  expect(view).toContain('Shadowrun character builder and campaign companion');
  expect(view).toContain('Download Chummer');
  expect(view).toContain('See what works today');
  expect(view).toContain('data-homepage-section="hero"');
  expect(view).toContain('data-homepage-section="product"');
  expect(view).toContain('data-homepage-section="flagship-promo"');
  expect(view).toContain('data-homepage-section="play-downloads"');
  expect(view).toContain('Everything your table reaches for first.');
  expect(view).toContain('A short look at the product.');
  expect(view).not.toContain('The city is moving.');
  expect(view).not.toContain('Open Black Ledger');
});
