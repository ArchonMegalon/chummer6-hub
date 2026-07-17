import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('horizons page defines the working lanes without turning into a front-door campaign surface', async ({ page }) => {
  await page.goto(`${baseUrl}/horizons`, { waitUntil: 'domcontentloaded' });

  await expect(page).toHaveTitle(/Horizons/i);
  const body = page.locator('body');
  await expect(page.locator('.minimal-kicker')).toHaveText('Horizons');
  await expect(body).toContainText('Not the front door');
  await expect(body).toContainText('Future work stays behind the main app');
  await expect(body).toContainText('Working lanes');
  await expect(body).toContainText('Stabilize now');
  await expect(body).toContainText('Play at the table next');
  await expect(body).toContainText('Living-world later');
  await expect(body).toContainText('Install parity, build flow, and support friction stay first');
  await expect(body).toContainText('Inventory, health, ammo, modifiers, quick rolls, and reconnect');
  await expect(body).toContainText('Opt-in world follow, heat, aftermath, and shared continuity');
  await expect(body).not.toContainText('Black Ledger');
  await expect(body).not.toContainText('Open Black Ledger');

  writeJsonArtifact('HORIZONS_WORKING_LANES.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/horizons',
    title_label: 'Horizons',
    lanes: [
      'Stabilize now',
      'Play at the table next',
      'Living-world later',
    ],
    frontdoor_posture: 'not_the_front_door',
  });
});
