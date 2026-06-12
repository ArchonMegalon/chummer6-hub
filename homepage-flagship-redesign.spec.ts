import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const landingViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'Landing.cshtml');

test('landing implements the flagship Black Ledger Gate structure', async () => {
  const view = readFileSync(landingViewPath, 'utf8');

  expect(view).toContain('Black Ledger command deck');
  expect(view).toContain('The city is moving.');
  expect(view).toContain('Open Black Ledger');
  expect(view).toContain('Download Chummer');
  expect(view).toContain('data-homepage-section="hero"');
  expect(view).toContain('data-homepage-section="score-strip"');
  expect(view).toContain('data-homepage-section="factions"');
  expect(view).toContain('data-homepage-section="flagship-promo"');
  expect(view).toContain('data-homepage-section="play-downloads"');
  expect(view).toContain('Build the runner. Run the table. Move the city.');
  expect(view).toContain('Ledger for the city. Downloads for the build. Play for the shell. Status for release health.');
});
