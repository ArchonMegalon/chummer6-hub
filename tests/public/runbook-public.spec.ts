import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('runbook public route stays available and surfaces primer export action', async ({ request, page }) => {
  const routeResponse = await request.get(`${baseUrl}/runbook`);
  const primerResponse = await request.get(`${baseUrl}/runbook/primers/new-runner-primer.json`);

  expect(routeResponse.status()).toBe(200);
  expect(primerResponse.status()).toBe(200);

  const primerPayload = await primerResponse.json();
  expect(primerPayload.style).toBe('Primer');
  expect(primerPayload.tour_action_href).toBe('/runbook/primers/new-runner-primer/export');
  expect(primerPayload.tour_action_label).toBe('Export Primer');
  expect(primerPayload.tour_href).toBe('/runbook/primers/new-runner-primer/export');
  expect(primerPayload.tour_open_in_new_tab).toBe(false);

  await page.goto(`${baseUrl}/runbook`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'RUNBOOK PRESS', exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText('RUNBOOK PRESS now ships real primers');
  await expect(page.locator('body')).toContainText('Open first primer');
  await expect(page.getByRole('link', { name: 'Export Primer' }).first()).toHaveAttribute('href', '/runbook/primers/new-runner-primer/export');

  writeJsonArtifact('RUNBOOK_ROUTE_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    route: '/runbook',
    primer_route: '/runbook/primers/new-runner-primer.json',
    primerPayload,
  });
});
