import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('black ledger globe mode switching and replay produce visible state changes', async ({ page }) => {
  await page.goto(`${baseUrl}/ledger/map#ledger-map`, { waitUntil: 'networkidle' });

  const root = page.locator('[data-black-ledger-geoscape-root]');
  await expect(root).toBeVisible();
  await expect(page.locator('#ledger-map')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Influence' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Conflict' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Recent changes' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Replay Turn 1' })).toBeVisible();

  const initialSignature = await root.getAttribute('data-render-signature');
  await page.getByRole('button', { name: 'Conflict' }).click();
  await expect(root).toHaveAttribute('data-current-mode', 'conflict');
  const conflictSignature = await root.getAttribute('data-render-signature');
  expect(conflictSignature).not.toEqual(initialSignature);

  await page.getByRole('button', { name: 'Replay Turn 1' }).click();
  await page.waitForTimeout(900);
  const replayState = await root.getAttribute('data-replay-state');
  expect(replayState).not.toEqual('idle');
  const replaySignature = await root.getAttribute('data-render-signature');
  expect(replaySignature).not.toEqual(conflictSignature);

  writeJsonArtifact('BLACK_LEDGER_GLOBE_MOTION.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/ledger/map#ledger-map',
    initial_signature: initialSignature,
    conflict_signature: conflictSignature,
    replay_signature: replaySignature,
    replay_state: replayState,
  });
});

test('black ledger globe honors reduced motion with step replay', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/ledger/map#ledger-map`, { waitUntil: 'networkidle' });

  const root = page.locator('[data-black-ledger-geoscape-root]');
  await expect(root).toHaveAttribute('data-reduced-motion', 'true');

  const states: string[] = [];
  for (let index = 0; index < 3; index += 1) {
    await page.getByRole('button', { name: 'Replay Turn 1' }).click();
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
