import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('public contact points to Discord and hides private intake', async ({ page }) => {
  await page.goto(`${baseUrl}/contact`, { waitUntil: 'domcontentloaded' });

  await expect(page.getByRole('heading', { name: 'Contact' })).toBeVisible();
  await expect(page.locator('body')).toContainText('Use the Chummer5 Discord server.');
  await expect(page.getByRole('link', { name: 'Open Discord' })).toBeVisible();
  await expect(page.locator('#support-intake')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Send support request' })).toHaveCount(0);

  writeJsonArtifact('CONTACT_PUBLIC_DISCORD_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    path: new URL(page.url()).pathname,
  });
});
