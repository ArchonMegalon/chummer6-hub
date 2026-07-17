import { devices, expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = (process.env.BASE_URL?.trim() || 'https://chummer.run').replace(/\/$/, '');

async function expectInteractiveNewRunnerRouteState(page: import('playwright/test').Page) {
  const appSurface = page.locator('section.browser-app-roster[data-route-family="app"]').first();
  await expect(appSurface).toBeVisible();
  await expect(appSurface).toHaveAttribute('data-active-workflow', 'build-lab');
  await expect(appSurface).toHaveAttribute('data-command', 'new-character');
  await expect(appSurface).toHaveAttribute('data-chummer-app-startup-command', 'new_character');

  const sharedShell = page.locator('[data-app-route-shared-shell="true"]').first();
  await expect(sharedShell).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'New runner' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Build Lab shell' })).toBeVisible();

  await expect(page.locator('#dialogBackdrop[data-dialog-id="dialog.new_character"]')).toHaveCount(1, { timeout: 20000 });
  await expect(page.locator('#dialogTitle')).toBeVisible({ timeout: 20000 });
  await expect(page.locator('button.menu-btn.classic-menu-button').filter({ hasText: 'File' })).toBeDisabled({ timeout: 20000 });
  await expect(page.locator('button.tool-btn.classic-tool-button').filter({ hasText: 'New' }).first()).toBeDisabled({ timeout: 20000 });
  await expect(page.locator('body')).not.toContainText('Your runners will appear here.');
}

async function gotoInteractiveNewRunnerRoute(page: import('playwright/test').Page) {
  await page.goto(`${baseUrl}/blazor/app?command=new_character`, { waitUntil: 'networkidle' });
  await expectInteractiveNewRunnerRouteState(page);
}

async function closeStartupDialog(page: import('playwright/test').Page) {
  await page.locator('#dialogClose').click();
  await expect(page.locator('#dialogBackdrop[data-dialog-id="dialog.new_character"]')).toHaveCount(0);
  await expect(page.locator('button.menu-btn.classic-menu-button').filter({ hasText: 'File' })).toBeEnabled();
  await expect(page.locator('button.tool-btn.classic-tool-button').filter({ hasText: 'New' }).first()).toBeEnabled();
}

async function reopenNewRunnerDialogFromFileMenu(page: import('playwright/test').Page) {
  await page.locator('button.menu-btn.classic-menu-button').filter({ hasText: 'File' }).click();
  const newRunnerMenuItem = page.locator('.menu-dropdown.classic-menu-dropdown button').filter({ hasText: 'New runner' }).first();
  await expect(newRunnerMenuItem).toBeEnabled();
  await newRunnerMenuItem.click();
  await expect(page.locator('#dialogBackdrop[data-dialog-id="dialog.new_character"]')).toHaveCount(1);
  await expect(page.locator('button.menu-btn.classic-menu-button').filter({ hasText: 'File' })).toBeDisabled();
}

async function expectBuildLabContinuationRoute(page: import('playwright/test').Page) {
  await page.getByRole('link', { name: 'Continue Build Lab' }).click();
  await page.waitForURL(/\/blazor\/app\?fixture=blue&tab=tab-create$/);

  const appSurface = page.locator('section.browser-app-roster[data-route-family="app"]').first();
  await expect(appSurface).toHaveAttribute('data-active-workflow', 'build-lab');
  await expect(appSurface).toHaveAttribute('data-tab', 'tab-create');
  await expect(page.getByRole('heading', { level: 1, name: 'Build Lab' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Build Lab shell' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Continue Build Lab' })).toBeVisible();
}

async function runNewRunnerRouteAudit(page: import('playwright/test').Page) {
  await gotoInteractiveNewRunnerRoute(page);
  await closeStartupDialog(page);
  await reopenNewRunnerDialogFromFileMenu(page);
}

async function expectAppRosterNewRunnerMenuRoute(page: import('playwright/test').Page) {
  const initialUrl = `${baseUrl}/blazor/app`;
  await page.goto(initialUrl, { waitUntil: 'domcontentloaded' });

  const appSurface = page.locator('section.browser-app-roster[data-route-family="app"]').first();
  await expect(appSurface).toBeVisible();
  await expect(appSurface).toHaveAttribute('data-command', 'none');
  await expect(page.getByRole('heading', { level: 1, name: 'Character Roster' })).toBeVisible();

  await page.locator('[data-app-menu-summary="file"]').first().click();
  const newRunner = page.locator('[data-app-menu-item="new-runner"]').first();
  const resolvedNewRunnerHref = await newRunner.getAttribute('href');
  await expect(newRunner).toHaveAttribute('href', 'app?command=new_character');
  await newRunner.click();

  await page.waitForURL(/\/blazor\/app\?command=new_character$/);
  await page.waitForLoadState('networkidle');
  await expectInteractiveNewRunnerRouteState(page);

  return {
    initial_url: initialUrl,
    resolved_new_runner_href: resolvedNewRunnerHref,
    final_url: page.url(),
    active_workflow: await appSurface.getAttribute('data-active-workflow'),
    command: await appSurface.getAttribute('data-command'),
    startup_command: await appSurface.getAttribute('data-chummer-app-startup-command'),
    dialog_count: await page.locator('#dialogBackdrop[data-dialog-id="dialog.new_character"]').count(),
    headline: ((await page.getByRole('heading', { level: 1, name: 'New runner' }).textContent()) || '').trim(),
    workflow_heading: ((await page.getByRole('heading', { level: 2, name: 'Build Lab shell' }).textContent()) || '').trim(),
    file_menu_locked_during_dialog: await page.locator('button.menu-btn.classic-menu-button').filter({ hasText: 'File' }).isDisabled(),
    new_tool_locked_during_dialog: await page.locator('button.tool-btn.classic-tool-button').filter({ hasText: 'New' }).first().isDisabled(),
  };
}

async function expectWorkbenchNewRunnerFallbackRoute(page: import('playwright/test').Page) {
  await page.goto(`${baseUrl}/blazor/workbench?workspace=blue-workspace&command=new_character`, { waitUntil: 'domcontentloaded' });

  const fallbackShell = page.locator('[data-ssr-workbench-fallback="true"]').first();
  await expect(fallbackShell).toBeVisible();
  await expect(fallbackShell).toHaveAttribute('data-command', 'new_character');
  await expect(fallbackShell.locator('section.desktop-dialog')).toHaveCount(1);
  await expect(fallbackShell.locator('section.desktop-dialog h2')).toHaveText('New runner');

  await page.locator('[data-app-menu-summary="file"]').first().click();
  await page.locator('[data-app-menu-item="new-runner"]').first().click();
  await page.waitForURL(/\/blazor\/workbench\?workspace=blue-workspace&tab=tab-create&command=new_character$/);

  const reopenedFallbackShell = page.locator('[data-ssr-workbench-fallback="true"]').first();
  await expect(reopenedFallbackShell).toBeVisible();
  await expect(reopenedFallbackShell).toHaveAttribute('data-command', 'new_character');
  await expect(reopenedFallbackShell).toHaveAttribute('data-tab', 'tab-create');
  await expect(reopenedFallbackShell.locator('section.desktop-dialog')).toHaveCount(1);
  await expect(reopenedFallbackShell.locator('section.desktop-dialog h2')).toHaveText('New runner');

  return {
    initialUrl: `${baseUrl}/blazor/workbench?workspace=blue-workspace&command=new_character`,
    resolvedNewRunnerHref: await page.locator('[data-app-menu-item="new-runner"]').first().getAttribute('href'),
    finalUrl: page.url(),
    reopenedDataCommand: await reopenedFallbackShell.getAttribute('data-command'),
    reopenedDataTab: await reopenedFallbackShell.getAttribute('data-tab'),
    dialogCount: await reopenedFallbackShell.locator('section.desktop-dialog').count(),
    dialogTitle: ((await reopenedFallbackShell.locator('section.desktop-dialog h2').first().textContent()) || '').trim(),
  };
}

test('blazor app new-character route renders the shared Build Lab shell contract', async ({ page }) => {
  test.setTimeout(90000);
  await runNewRunnerRouteAudit(page);
});

test('blazor app new-character route keeps the shared Build Lab shell contract on Android', async ({ browser }) => {
  test.setTimeout(90000);

  const context = await browser.newContext({
    ...devices['Pixel 7'],
  });
  const page = await context.newPage();

  try {
    await runNewRunnerRouteAudit(page);
  } finally {
    await context.close();
  }
});

test('blazor app roster File > New runner transitions into the new-runner Build Lab route', async ({ page }) => {
  test.setTimeout(90000);
  await expectAppRosterNewRunnerMenuRoute(page);
});

test('blazor workbench new-runner menu keeps the new-character dialog route alive', async ({ page }) => {
  test.setTimeout(90000);
  await gotoInteractiveNewRunnerRoute(page);
  const fileMenuButton = page.locator('button.menu-btn.classic-menu-button').filter({ hasText: 'File' });
  const newToolButton = page.locator('button.tool-btn.classic-tool-button').filter({ hasText: 'New' }).first();
  const startupDialogTitle = ((await page.locator('#dialogTitle').textContent()) || '').trim();
  const fileMenuLockedDuringDialog = await fileMenuButton.isDisabled();
  const newToolLockedDuringDialog = await newToolButton.isDisabled();
  await closeStartupDialog(page);
  const fileMenuEnabledAfterClose = await fileMenuButton.isEnabled();
  const newToolButtonEnabledAfterClose = await newToolButton.isEnabled();
  await reopenNewRunnerDialogFromFileMenu(page);
  const reopenedDialogTitle = ((await page.locator('#dialogTitle').textContent()) || '').trim();
  const reopenedDialogVisible = await page.locator('#dialogBackdrop[data-dialog-id="dialog.new_character"]').count();

  const appRosterTransitionSummary = await expectAppRosterNewRunnerMenuRoute(page);
  const fallbackSummary = await expectWorkbenchNewRunnerFallbackRoute(page);
  writeJsonArtifact('BLAZOR_NEW_RUNNER_MENU.generated.json', {
    contractName: 'chummer.blazor_new_runner_menu.v1',
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    app_route: {
      initial_url: `${baseUrl}/blazor/app?command=new_character`,
      startup_dialog_title: startupDialogTitle,
      file_menu_locked_during_dialog: fileMenuLockedDuringDialog,
      new_tool_locked_during_dialog: newToolLockedDuringDialog,
      file_menu_enabled_after_close: fileMenuEnabledAfterClose,
      new_tool_enabled_after_close: newToolButtonEnabledAfterClose,
      reopened_dialog_title: reopenedDialogTitle,
      reopened_dialog_visible: reopenedDialogVisible,
    },
    app_roster_transition: {
      initial_url: appRosterTransitionSummary.initial_url,
      resolved_new_runner_href: appRosterTransitionSummary.resolved_new_runner_href,
      final_url: appRosterTransitionSummary.final_url,
      active_workflow: appRosterTransitionSummary.active_workflow,
      command: appRosterTransitionSummary.command,
      startup_command: appRosterTransitionSummary.startup_command,
      dialog_count: appRosterTransitionSummary.dialog_count,
      headline: appRosterTransitionSummary.headline,
      workflow_heading: appRosterTransitionSummary.workflow_heading,
      file_menu_locked_during_dialog: appRosterTransitionSummary.file_menu_locked_during_dialog,
      new_tool_locked_during_dialog: appRosterTransitionSummary.new_tool_locked_during_dialog,
    },
    workbench_fallback_route: {
      initial_url: fallbackSummary.initialUrl,
      resolved_new_runner_href: fallbackSummary.resolvedNewRunnerHref,
      final_url: fallbackSummary.finalUrl,
      reopened_data_command: fallbackSummary.reopenedDataCommand,
      reopened_data_tab: fallbackSummary.reopenedDataTab,
      dialog_count: fallbackSummary.dialogCount,
      dialog_title: fallbackSummary.dialogTitle,
    },
  });
});
