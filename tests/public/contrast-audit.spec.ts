import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const cssPath = path.join(repoRoot, 'Chummer.Run.Api', 'wwwroot', 'css', 'site.css');

test('public front-door surfaces keep readable contrast tokens and no white-on-gray regression', async () => {
  const css = readFileSync(cssPath, 'utf8');

  expect(css).toContain('--text-on-strong: #f7fbff;');
  expect(css).toContain('--text-on-muted: #10243f;');
  expect(css).toContain('--link-strong: #0f4fcc;');
  expect(css).toContain('.route-landing .section-copy');
  expect(css).toContain('.route-landing .access-band .editorial-title');
  expect(css).toContain('.route-landing .access-band .inline-link');
  expect(css).toContain('.route-landing .site-sidebar__nav a');
  expect(css).toContain('.route-landing .muted-copy');

  expect(css).not.toContain('color: #fff; background: #ccc;');
  expect(css).not.toContain('.route-landing .site-sidebar__nav a {\n  background: rgba(45, 114, 255, 0.05);\n  color: #fff;');
  expect(css).not.toContain('.route-landing .muted-copy {\n  color: #fff;');
});
