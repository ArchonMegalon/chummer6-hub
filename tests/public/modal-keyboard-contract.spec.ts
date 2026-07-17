import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test } from 'playwright/test';

const repoRoot = process.cwd();
const siteScriptPath = path.join(repoRoot, 'Chummer.Run.Api/wwwroot/js/site.js');
const homeViewPath = path.join(repoRoot, 'Chummer.Run.Api/Views/PublicLanding/Home.cshtml');
const layoutViewPath = path.join(repoRoot, 'Chummer.Run.Api/Views/Shared/_Layout.cshtml');
const liveLinksSpecPath = path.join(repoRoot, 'tests/public/all-live-links.spec.ts');

test('the public interaction audit can target a local release candidate', () => {
  const liveLinksSpec = readFileSync(liveLinksSpecPath, 'utf8');

  expect(liveLinksSpec).toContain('process.env.BASE_URL ?? process.env.CHUMMER_HUB_BASE_URL');
  expect(liveLinksSpec).not.toContain("const baseUrl = 'https://chummer.run';");
});

test('the shared skip link transfers focus to the main landmark', async ({ page }) => {
  const layoutView = readFileSync(layoutViewPath, 'utf8');
  expect(layoutView).toContain('<main id="main" class="site-main" tabindex="-1">');

  await page.setContent(`
    <a class="skip-link" href="#main">Skip to content</a>
    <main id="main" class="site-main" tabindex="-1">
      <h1>Page content</h1>
    </main>
  `);

  await page.locator('.skip-link').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();
});

test('shared modal binding traps keyboard focus, closes on Escape, and restores the opener', async ({ page }) => {
  await page.setContent(`
    <main>
      <button id="open" type="button">Open setup</button>
      <a id="background-link" href="#outside">Background link</a>
    </main>
    <div id="setup-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" hidden>
      <div>
        <h2 id="dialog-title">Finish setup</h2>
        <label for="display-name">Display name</label>
        <input id="display-name" />
        <button id="next" type="button">Next</button>
        <button id="close" type="button">Close</button>
      </div>
    </div>
  `);
  await page.addScriptTag({ path: siteScriptPath });
  await page.evaluate(() => {
    const ui = (window as unknown as {
      ChummerUi: {
        bindModalDialog: (
          dialog: HTMLElement,
          options: Record<string, unknown>,
        ) => unknown;
      };
    }).ChummerUi;
    const dialog = document.getElementById('setup-dialog');
    const opener = document.getElementById('open');
    const closer = document.getElementById('close');
    if (!dialog || !opener || !closer) {
      throw new Error('modal fixture is incomplete');
    }

    ui.bindModalDialog(dialog, {
      openButtons: [opener],
      closeButtons: [closer],
      initialFocus: '#display-name',
    });
  });

  const opener = page.locator('#open');
  const dialog = page.locator('#setup-dialog');
  const firstField = page.locator('#display-name');
  const closeButton = page.locator('#close');

  await opener.click();
  await expect(dialog).toBeVisible();
  await expect(firstField).toBeFocused();
  await expect(page.locator('body')).toHaveClass(/\bdialog-open\b/);

  await closeButton.focus();
  await page.keyboard.press('Tab');
  await expect(firstField).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(closeButton).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(page.locator('body')).not.toHaveClass(/\bdialog-open\b/);
  await expect(opener).toBeFocused();
});

test('account setup uses the shared keyboard modal binding', () => {
  const homeView = readFileSync(homeViewPath, 'utf8');

  expect(homeView).toContain('ui.bindModalDialog(dialog');
  expect(homeView).toContain('initialFocus: "#onboardingDisplayName"');
});
