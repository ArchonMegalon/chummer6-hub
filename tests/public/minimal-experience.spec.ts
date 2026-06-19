import { expect, test } from 'playwright/test';
import { writeJsonArtifact, writeMarkdownArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('public surfaces stay minimal and first-task oriented', async ({ browser }) => {
  test.setTimeout(180000);
  const failures: string[] = [];
  const results: Array<Record<string, unknown>> = [];

  const desktop = await browser.newPage({ baseURL: baseUrl, viewport: { width: 1366, height: 768 } });

  await desktop.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  const navPanelOpen = await desktop.evaluate(() => document.body.classList.contains('nav-panel-open'));
  if (navPanelOpen) {
    failures.push('homepage: navigation panel is open by default');
  }
  await expect(desktop.locator('.minimal-hero h1')).toContainText('Chummer');
  await expect(desktop.locator('.minimal-hero__lead')).toContainText('Build and maintain Shadowrun characters');
  const heroActions = await desktop.locator('.minimal-hero .minimal-actions a.button-like').allTextContents();
  if (heroActions.map((text) => text.trim()).join('|') !== 'Stable|Nightly') {
    failures.push(`homepage: expected Stable then Nightly hero actions, found ${heroActions.join(', ')}`);
  }
  const heroImage = desktop.locator('.minimal-hero__visual img');
  await expect(heroImage).toBeVisible();
  const heroImageComplete = await heroImage.evaluate((node) => {
    const image = node as HTMLImageElement;
    return image.complete && image.naturalWidth > 400 && image.naturalHeight > 200;
  });
  if (!heroImageComplete) {
    failures.push('homepage: hero image did not load with useful dimensions');
  }
  await expect(desktop.locator('[data-homepage-section="downloads"]')).toContainText('Get the app');
  results.push({ surface: 'home', nav_panel_open: navPanelOpen, hero_image_loaded: heroImageComplete });

  await desktop.goto(`${baseUrl}/downloads`, { waitUntil: 'domcontentloaded' });
  const stableLane = desktop.locator('#stable');
  const nightlyLane = desktop.locator('#nightly');
  await expect(stableLane).toBeVisible();
  await expect(nightlyLane).toBeVisible();
  await expect(stableLane.getByRole('link', { name: 'Windows' })).toBeVisible();
  await expect(stableLane.getByRole('link', { name: 'Linux' })).toBeVisible();
  await expect(nightlyLane.getByRole('link', { name: 'Windows' })).toBeVisible();
  await expect(nightlyLane.getByRole('link', { name: 'Linux' })).toBeVisible();
  const downloadsText = await desktop.locator('body').innerText();
  for (const forbidden of ['Signed-in download', 'portable', 'recommended download', 'proof', 'receipt']) {
    if (downloadsText.toLowerCase().includes(forbidden.toLowerCase())) {
      failures.push(`downloads: contains retired copy "${forbidden}"`);
    }
  }
  results.push({ surface: 'downloads', stable_visible: true, nightly_visible: true });

  await desktop.goto(`${baseUrl}/status`, { waitUntil: 'domcontentloaded' });
  const decisionSurface = desktop.locator('[data-status-surface="decision-surface"]');
  const decisionCards = decisionSurface.locator('.route-choice-card');
  const nextActions = decisionSurface.locator('.minimal-actions a.button-like');
  await expect(decisionSurface).toBeVisible();
  await expect(decisionSurface).toContainText('Release');
  await expect(decisionSurface).toContainText('Downloads');
  const cardCount = await decisionCards.count();
  if (cardCount !== 1) {
    failures.push(`status: expected exactly 1 decision card, found ${cardCount}`);
  }
  const nextActionCount = await nextActions.count();
  if (nextActionCount !== 3) {
    failures.push(`status: expected exactly 3 next actions, found ${nextActionCount}`);
  }
  const statusText = await desktop.locator('body').innerText();
  for (const forbidden of ['Signed-in return', 'Status poster', 'At a glance', 'Release and next step.', 'Current caution.']) {
    if (statusText.includes(forbidden)) {
      failures.push(`status: contains retired secondary surface "${forbidden}"`);
    }
  }
  results.push({ surface: 'status', decision_card_count: cardCount, next_action_count: nextActionCount });

  await desktop.close();

  writeJsonArtifact('MINIMAL_EXPERIENCE_GATE.generated.json', {
    generated_at_utc: new Date().toISOString(),
    base_url: baseUrl,
    status: failures.length === 0 ? 'pass' : 'fail',
    verdict: failures.length === 0 ? 'READY' : 'NOT_READY',
    failures,
    results,
  });

  writeMarkdownArtifact(
    'MINIMAL_EXPERIENCE_GATE.md',
    [
      '# Minimal Experience Gate',
      '',
      `- Generated: ${new Date().toISOString()}`,
      `- Base URL: ${baseUrl}`,
      '- Checks: nav closed by default, homepage starts with Stable and Nightly, downloads exposes Windows and Linux lane buttons, one status decision card plus one next-action rail.',
      '',
      ...results.map((result) => `- ${String(result.surface)} checked`),
      ...(failures.length > 0 ? ['', '## Failures', '', ...failures.map((failure) => `- ${failure}`)] : []),
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
