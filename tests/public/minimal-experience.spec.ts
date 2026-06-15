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
  await expect(desktop.locator('.launch-hero__actions a.button-like').first()).toContainText('Open Black Ledger');
  await expect(desktop.locator('[data-homepage-section="play-downloads"]')).toContainText('Install, play, or open the city.');
  const homeVideo = desktop.locator('.flagship-promo-player__video');
  await expect(homeVideo).toBeVisible();
  const homePlayback = await homeVideo.evaluate(async (node) => {
    const video = node as HTMLVideoElement;
    video.muted = true;
    video.currentTime = 0;
    await video.play();
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    video.pause();
    return {
      source_count: video.querySelectorAll('source').length,
      track_count: video.querySelectorAll('track').length,
      current_time: video.currentTime,
      poster: video.poster,
    };
  });
  if (homePlayback.source_count < 2 || homePlayback.track_count < 1 || homePlayback.current_time <= 0) {
    failures.push('homepage: flagship reel does not expose working playback with sources, captions, and advancing time');
  }
  results.push({ surface: 'home', nav_panel_open: navPanelOpen, media_playback: homePlayback });

  await desktop.goto(`${baseUrl}/downloads`, { waitUntil: 'domcontentloaded' });
  const recommendedCard = desktop.locator('#recommended-download');
  const filterAccordion = desktop.locator('[aria-label="Download filters"] details.release-accordion').first();
  const recommendedTop = (await recommendedCard.boundingBox())?.y ?? Number.POSITIVE_INFINITY;
  const filterTop = (await filterAccordion.boundingBox())?.y ?? Number.POSITIVE_INFINITY;
  const filtersOpen = await filterAccordion.evaluate((node) => (node as HTMLDetailsElement).open);
  if (filterTop <= recommendedTop) {
    failures.push('downloads: filter controls appear before the recommended install path');
  }
  if (filtersOpen) {
    failures.push('downloads: filter controls are open by default');
  }
  results.push({ surface: 'downloads', recommended_top: recommendedTop, filter_top: filterTop, filters_open: filtersOpen });

  await desktop.goto(`${baseUrl}/status`, { waitUntil: 'domcontentloaded' });
  const decisionSurface = desktop.locator('[data-status-surface="decision-surface"]');
  const decisionCards = decisionSurface.locator('.route-choice-card');
  const nextActions = decisionSurface.locator('.stacked-actions a.button-like');
  await expect(decisionSurface).toBeVisible();
  await expect(decisionSurface).toContainText('Release, caution, next step.');
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

  await desktop.goto(`${baseUrl}/ledger/map`, { waitUntil: 'domcontentloaded' });
  const ledgerText = await desktop.locator('body').innerText();
  const newsroomLinks = desktop.getByRole('link', { name: 'Open newsroom' });
  const newsroomLinkCount = await newsroomLinks.count();
  if (newsroomLinkCount !== 1) {
    failures.push(`ledger: expected exactly 1 "Open newsroom" link, found ${newsroomLinkCount}`);
  }
  const emptyEditorialParagraphs = await desktop.locator('p.editorial-copy').evaluateAll((nodes) =>
    nodes.filter((node) => !(node.textContent || '').trim()).length,
  );
  if (emptyEditorialParagraphs > 0) {
    failures.push(`ledger: found ${emptyEditorialParagraphs} empty editorial paragraphs`);
  }
  for (const forbidden of ['Board signal:', 'Turn source:', 'Production notes', 'City note:', 'City pulse:', 'Built from', 'deterministic board', 'Linked through', 'Turn record:', 'Scene notes']) {
    if (ledgerText.includes(forbidden)) {
      failures.push(`ledger: contains provenance language "${forbidden}"`);
    }
  }
  results.push({ surface: 'ledger-map', cleaned_language: true, newsroom_link_count: newsroomLinkCount, empty_editorial_paragraphs: emptyEditorialParagraphs });

  await desktop.goto(`${baseUrl}/ledger/newsroom`, { waitUntil: 'domcontentloaded' });
  const newsroomVideo = desktop.locator('.ledger-newsreel-broadcast__video');
  await expect(newsroomVideo).toBeVisible();
  const newsroomPlayback = await newsroomVideo.evaluate(async (node) => {
    const video = node as HTMLVideoElement;
    video.muted = true;
    video.currentTime = 0;
    await video.play();
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    video.pause();
    return {
      source_count: video.querySelectorAll('source').length,
      track_count: video.querySelectorAll('track').length,
      current_time: video.currentTime,
      poster: video.poster,
    };
  });
  if (newsroomPlayback.source_count < 2 || newsroomPlayback.track_count < 1 || newsroomPlayback.current_time <= 0) {
    failures.push('ledger-newsroom: broadcast video does not expose working playback with sources, captions, and advancing time');
  }
  results.push({ surface: 'ledger-newsroom', media_playback: newsroomPlayback });

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
      '- Checks: nav closed by default, recommended install before filters, one status decision card plus one next-action rail, no public ledger provenance wording.',
      '',
      ...results.map((result) => `- ${String(result.surface)} checked`),
      ...(failures.length > 0 ? ['', '## Failures', '', ...failures.map((failure) => `- ${failure}`)] : []),
    ].join('\n'),
  );

  expect(failures, failures.join('\n')).toEqual([]);
});
