import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('guest support case submission reaches the confirmation route', async ({ page }) => {
  await page.goto(`${baseUrl}/contact`, { waitUntil: 'domcontentloaded' });

  await expect(page.getByRole('heading', { name: 'Contact' })).toBeVisible();
  await page.selectOption('#supportKind', 'bug_report');
  await page.fill('#supportTitle', 'Public contact flow E2E');
  await page.fill('#supportSummary', 'Guest support submission should reach the confirmation route.');
  await page.fill('#supportDetail', 'This browser test submits the public support form as a guest and expects the confirmation page to resolve cleanly.');
  await page.fill('#supportReplyEmail', 'guest-support-e2e@example.test');

  await page.getByRole('button', { name: 'Send support request' }).click();
  await page.waitForURL(/\/contact\/submitted\/support_case_/);

  await expect(page.getByRole('heading', { name: 'Support case received' })).toBeVisible();
  await expect(page.locator('body')).toContainText('Guest follow-up stays on the reply email you provided');
  await expect(page.getByRole('link', { name: 'Return to help' })).toBeVisible();

  writeJsonArtifact('CONTACT_SUBMIT_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    submitted_path: new URL(page.url()).pathname,
  });
});
