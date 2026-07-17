import path from 'node:path';
import { expect, test } from 'playwright/test';

const siteScriptPath = path.join(process.cwd(), 'Chummer.Run.Api/wwwroot/js/site.js');

test('shared async notices expose success and error updates to assistive technology', async ({ page }) => {
  await page.setContent(`
    <main>
      <p id="notice" class="muted-copy" hidden></p>
      <button id="save" type="button">Save settings</button>
    </main>
  `);
  await page.addScriptTag({ path: siteScriptPath });

  const notice = page.locator('#notice');
  const save = page.locator('#save');

  await page.evaluate(() => {
    window.ChummerUi.setNotice(document.getElementById('notice'), 'Settings saved.');
  });
  await expect(notice).toBeVisible();
  await expect(notice).toHaveAttribute('role', 'status');
  await expect(notice).toHaveAttribute('aria-live', 'polite');
  await expect(notice).toHaveAttribute('aria-atomic', 'true');
  await expect(notice).toHaveClass(/status-copy--success/);

  await page.evaluate(() => {
    window.ChummerUi.setNotice(document.getElementById('notice'), 'Settings could not be saved.', true);
  });
  await expect(notice).toHaveText('Settings could not be saved.');
  await expect(notice).toHaveAttribute('role', 'alert');
  await expect(notice).toHaveAttribute('aria-live', 'assertive');
  await expect(notice).toHaveAttribute('aria-atomic', 'true');
  await expect(notice).toHaveClass(/status-copy--error/);

  await page.evaluate(() => {
    window.ChummerUi.setButtonBusy(document.getElementById('save'), true, 'Saving...');
  });
  await expect(save).toBeDisabled();
  await expect(save).toHaveText('Saving...');
  await expect(save).toHaveAttribute('aria-busy', 'true');

  await page.evaluate(() => {
    window.ChummerUi.setButtonBusy(document.getElementById('save'), false, 'Saving...');
  });
  await expect(save).toBeEnabled();
  await expect(save).toHaveText('Save settings');
  await expect(save).not.toHaveAttribute('aria-busy', 'true');
});
