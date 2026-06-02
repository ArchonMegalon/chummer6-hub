import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger globe mode switching and replay produce visible state changes', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map#ledger-map`, { waitUntil: 'domcontentloaded' });

  const root = page.locator('#ledger-map [data-black-ledger-geoscape-root]').first();
  await expect(root).toBeVisible();
  await expect(page.locator('#ledger-map')).toBeVisible();
  await expect(root.getByRole('button', { name: 'Influence' })).toBeVisible();
  const modeButtons = root.locator('.black-ledger-geoscape__modes button');
  await expect(modeButtons).toHaveCount(7);
  await expect(root.getByRole('button', { name: 'Replay pressure' })).toBeVisible();

  const initialSignature = await root.getAttribute('data-render-signature');
  const alternateMode = modeButtons.nth(1);
  const alternateLabel = (await alternateMode.textContent())?.trim() || '';
  await alternateMode.click();
  const currentMode = await root.getAttribute('data-current-mode');
  expect(currentMode).toBeTruthy();
  expect(currentMode).not.toEqual('influence');
  const alternateSignature = await root.getAttribute('data-render-signature');
  expect(alternateSignature).not.toEqual(initialSignature);

  await root.getByRole('button', { name: 'Replay pressure' }).click();
  await page.waitForTimeout(900);
  const replayState = await root.getAttribute('data-replay-state');
  expect(replayState).not.toEqual('idle');
  const replaySignature = await root.getAttribute('data-render-signature');
  expect(replaySignature).not.toEqual(alternateSignature);

  writeJsonArtifact('BLACK_LEDGER_GLOBE_MOTION.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map#ledger-map',
    initial_signature: initialSignature,
    alternate_mode_label: alternateLabel,
    alternate_signature: alternateSignature,
    replay_signature: replaySignature,
    replay_state: replayState,
  });
});

test('black ledger globe honors reduced motion with step replay', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/ledger/map#ledger-map`, { waitUntil: 'domcontentloaded' });

  const root = page.locator('#ledger-map [data-black-ledger-geoscape-root]').first();
  await expect(root).toHaveAttribute('data-reduced-motion', 'true');

  const states: string[] = [];
  for (let index = 0; index < 3; index += 1) {
    await root.getByRole('button', { name: 'Replay pressure' }).click();
    states.push((await root.getAttribute('data-replay-state')) ?? '');
  }

  writeJsonArtifact('BLACK_LEDGER_GLOBE_REDUCED_MOTION.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map#ledger-map',
    reduced_motion: true,
    replay_states: states,
  });
});
