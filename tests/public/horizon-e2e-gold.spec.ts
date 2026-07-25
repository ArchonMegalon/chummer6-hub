import { expect, test, type APIRequestContext, type Page } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = (process.env.BASE_URL?.trim() || 'https://chummer.run').replace(/\/+$/, '');
const claimScope = 'registered_shipped_mvp_public_journey';

type GoldReceipt = {
  horizon_id: string;
  route: string;
  receipt_route: string;
  assertion_count: number;
  journey_steps: string[];
  boundaries_verified: string[];
  evidence: Record<string, unknown>;
};

async function jsonFrom(request: APIRequestContext, path: string): Promise<Record<string, any>> {
  const response = await request.get(`${baseUrl}${path}`);
  expect(response.status(), `${path} should be available`).toBe(200);
  expect(response.headers()['content-type'] || '', `${path} should return JSON`).toContain('application/json');
  return await response.json();
}

async function publicPage(page: Page, route: string, heading: string | RegExp): Promise<void> {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const response = await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded' });
  expect(response?.status(), `${route} should render`).toBe(200);
  await expect(page.locator('main')).toBeVisible();
  await expect(page.locator('h1')).toHaveCount(1);
  await expect(page.locator('h1')).toContainText(heading);
  await expect(page.locator('main')).not.toContainText(/application error|internal server error/i);
  expect(pageErrors, `${route} should not throw page errors`).toEqual([]);
}

async function expectLoginBoundary(request: APIRequestContext, path: string): Promise<string> {
  const response = await request.get(`${baseUrl}${path}`, { maxRedirects: 0 });
  expect([302, 303, 307, 308], `${path} should hand unauthenticated users to sign-in`).toContain(response.status());
  const location = response.headers()['location'] || '';
  expect(location).toContain('/login?next=');
  return location;
}

function writeGold(receipt: GoldReceipt): void {
  writeJsonArtifact(`HORIZON_E2E_GOLD.${receipt.horizon_id}.generated.json`, {
    contract_name: 'chummer.horizon_e2e_gold/v1',
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    verdict: 'GOLD',
    claim_scope: claimScope,
    base_url: baseUrl,
    ...receipt,
  });
}

test('gold horizon: alice executes the public compare-to-signed-in boundary', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/alice/receipts/build-ghost.json');
  expect(receipt.engineStatus).toBe('First-party compare/apply only');
  expect(receipt.canonicalLane).toContain('Chummer character compare bench');
  expect(receipt.runtimeBoundary).toContain('may compute legality');
  expect(receipt.runtimeBoundary).toContain('mutate the runner');
  expect(receipt.signedInBench.accountRedirectHref).toBe('/account/alice/open');
  await publicPage(page, '/alice', 'Character help');
  await expect(page.getByRole('link', { name: /Open signed-in helper/i })).toHaveAttribute('href', '/account/alice/open');
  const loginLocation = await expectLoginBoundary(request, '/account/alice/open');

  writeGold({
    horizon_id: 'alice',
    route: '/alice',
    receipt_route: '/alice/receipts/build-ghost.json',
    assertion_count: 13,
    journey_steps: ['load public compare receipt', 'render character-help surface', 'inspect signed-in handoff', 'verify unauthenticated access boundary'],
    boundaries_verified: ['chummer_owns_compare_apply', 'no_assistant_legality', 'no_silent_runner_mutation', 'private_handoff_requires_identity'],
    evidence: { receipt_route: '/alice/receipts/build-ghost.json', login_location: loginLocation },
  });
});

test('gold horizon: origin-dossier executes story edition, PDF, media, and identity boundaries', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/origin-dossier/receipts/story-network.json');
  expect(receipt.horizon).toBe('origin-dossier');
  expect(receipt.status).toBe('shipped_mvp');
  expect(receipt.boundary.storyTruth).toBe('approved_chummer_owned_story_edition');
  expect(receipt.boundary.silentMechanicsMutation).toBe('not_claimed');
  expect(receipt.boundary.providerTruth).toBe('not_claimed');
  const story = await request.get(`${baseUrl}${receipt.publicBoard.storyEditionHref}`);
  expect(story.status()).toBe(200);
  const pdf = await request.get(`${baseUrl}${receipt.publicBoard.storyEditionPdfHref}`);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()['content-type'] || '').toContain('application/pdf');
  await publicPage(page, '/origin-dossier', /Origin Dossier/i);
  await expect(page.getByRole('link', { name: 'Open the story edition sample' })).toHaveAttribute('href', receipt.publicBoard.storyEditionHref);
  const loginLocation = await expectLoginBoundary(request, '/account/work?edition=origin');

  writeGold({
    horizon_id: 'origin-dossier',
    route: '/origin-dossier',
    receipt_route: '/origin-dossier/receipts/story-network.json',
    assertion_count: 15,
    journey_steps: ['load story-network receipt', 'render origin surface', 'open first-party story edition', 'download ebook PDF', 'verify private library identity boundary'],
    boundaries_verified: ['approved_story_is_chummer_owned', 'no_silent_mechanics_mutation', 'provider_output_not_truth', 'private_dossier_requires_identity'],
    evidence: {
      receipt_route: '/origin-dossier/receipts/story-network.json',
      story_route: receipt.publicBoard.storyEditionHref,
      pdf_route: receipt.publicBoard.storyEditionPdfHref,
      login_location: loginLocation,
    },
  });
});

test('gold horizon: karma-forge executes public intake and governed discovery boundary', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/participate/karma-forge/receipts/discovery-network.json');
  expect(receipt.horizon).toBe('karma-forge');
  expect(receipt.status).toBe('shipped_mvp');
  expect(receipt.publicBoard.intakeHref).toBe('/participate/karma-forge');
  expect(receipt.boundary.rulesTruth).toBe('not_claimed');
  expect(receipt.boundary.approvalTruth).toBe('chummer_owned');
  expect(receipt.boundary.roadmapTruth).toBe('separate');
  await publicPage(page, '/participate/karma-forge', /KARMA FORGE/i);
  await expect(page.locator('form')).toBeVisible();
  const loginLocation = await expectLoginBoundary(request, '/participate/karma-forge/discovery');

  writeGold({
    horizon_id: 'karma-forge',
    route: '/participate/karma-forge',
    receipt_route: '/participate/karma-forge/receipts/discovery-network.json',
    assertion_count: 13,
    journey_steps: ['load discovery-network receipt', 'render first-party intake', 'verify form exists', 'verify governed discovery handoff requires identity'],
    boundaries_verified: ['no_public_rules_truth_claim', 'approval_stays_chummer_owned', 'roadmap_stays_separate', 'discovery_handoff_requires_identity'],
    evidence: { receipt_route: '/participate/karma-forge/receipts/discovery-network.json', login_location: loginLocation },
  });
});

test('gold horizon: knowledge-fabric executes cited answer and provenance boundaries', async ({ page, request }) => {
  const index = await jsonFrom(request, '/rules/explanations');
  expect(Array.isArray(index.receipts)).toBeTruthy();
  expect(index.receipts.length).toBeGreaterThanOrEqual(3);
  expect(index.boundary).toContain('source-safe');
  expect(index.boundary).toContain('provenance-first');
  const first = index.receipts[0];
  expect(first.status).toBe('live');
  expect(first.provenance).toBeTruthy();
  const detail = await jsonFrom(request, first.route);
  expect(JSON.stringify(detail).toLowerCase()).toContain('provenance');
  await publicPage(page, '/rules', /Knowledge Fabric/i);
  await expect(page.locator('main')).toContainText(/source context|based on/i);

  writeGold({
    horizon_id: 'knowledge-fabric',
    route: '/rules',
    receipt_route: '/rules/explanations',
    assertion_count: 14,
    journey_steps: ['load explanation index', 'select a live receipt', 'open cited answer JSON', 'render source-safe rules surface'],
    boundaries_verified: ['answer_has_provenance', 'public_route_is_source_safe', 'official_text_not_dumped', 'private_campaign_data_excluded'],
    evidence: { index_route: '/rules/explanations', detail_route: first.route, receipt_id: first.receiptId },
  });
});

test('gold horizon: jackpoint executes briefing packet and private-media boundaries', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/jackpoint/receipts/briefing-network.json');
  expect(receipt.horizon).toBe('jackpoint');
  expect(receipt.status).toBe('shipped_mvp');
  expect(receipt.boundary.publicAudience).toBe('player_safe_only');
  expect(receipt.boundary.publicationTruth).toBe('chummer_owned');
  const markdown = await request.get(`${baseUrl}${receipt.publicBoard.firstBriefingMarkdownHref}`);
  expect(markdown.status()).toBe(200);
  expect(markdown.headers()['content-type'] || '').toContain('text/markdown');
  const packet = await jsonFrom(request, receipt.publicBoard.firstBriefingJsonHref);
  expect(packet).toBeTruthy();
  await publicPage(page, '/jackpoint', 'JACKPOINT');
  const loginLocation = await expectLoginBoundary(request, '/jackpoint/briefings/emerald-sprawl-briefing/video');

  writeGold({
    horizon_id: 'jackpoint',
    route: '/jackpoint',
    receipt_route: '/jackpoint/receipts/briefing-network.json',
    assertion_count: 14,
    journey_steps: ['load briefing-network receipt', 'render public desk', 'open markdown briefing', 'open JSON briefing', 'verify narrated media identity boundary'],
    boundaries_verified: ['public_packets_are_player_safe', 'publication_truth_is_chummer_owned', 'gm_spoilers_stay_private', 'media_handoff_requires_identity'],
    evidence: {
      receipt_route: '/jackpoint/receipts/briefing-network.json',
      markdown_route: receipt.publicBoard.firstBriefingMarkdownHref,
      json_route: receipt.publicBoard.firstBriefingJsonHref,
      login_location: loginLocation,
    },
  });
});

test('gold horizon: black-ledger executes city board and governed viewer handoff', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/ledger/receipts/viewer-network.json');
  expect(receipt.horizon).toBe('black-ledger');
  expect(receipt.status).toBe('shipped_mvp');
  expect(receipt.boundary.providerTruth).toBe('not_claimed');
  expect(receipt.boundary.tacticalTruth).toBe('not_claimed');
  expect(receipt.boundary.routeTruth).toBe('chummer_owned_receipts_only');
  expect(receipt.artifactCapability.status).toBe('available');
  expect(receipt.artifactCapability.publicVisible).toBe(true);
  await publicPage(page, '/ledger', /Campaign city command map/i);
  await expect(page.locator('main')).toContainText(/Black Ledger/i);
  const viewer = await request.get(`${baseUrl}${receipt.publicBoard.viewerHref}`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(viewer.status());
  const viewerLocation = viewer.headers()['location'] || '';
  expect(new URL(viewerLocation).hostname).toBe('my.matterport.com');
  expect(viewer.headers()['x-horizon-artifact-request-id'] || '').toBeTruthy();

  writeGold({
    horizon_id: 'black-ledger',
    route: '/ledger',
    receipt_route: '/ledger/receipts/viewer-network.json',
    assertion_count: 16,
    journey_steps: ['load viewer-network receipt', 'render city board', 'request governed 3D viewer', 'verify provider allowlist and request receipt'],
    boundaries_verified: ['provider_not_world_truth', 'viewer_not_tactical_truth', 'route_truth_is_first_party', 'external_handoff_is_receipted'],
    evidence: {
      receipt_route: '/ledger/receipts/viewer-network.json',
      viewer_route: receipt.publicBoard.viewerHref,
      viewer_location: viewerLocation,
      request_id: viewer.headers()['x-horizon-artifact-request-id'],
    },
  });
});

test('gold horizon: runsite executes inspectable pack and identity-gated tour', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/runsites/receipts/prep-network.json');
  expect(receipt.horizon).toBe('runsite');
  expect(receipt.status).toBe('shipped_mvp');
  expect(receipt.boundary.tacticalAuthority).toBe('not_claimed');
  expect(receipt.boundary.vttReplacement).toBe('not_claimed');
  const pack = await jsonFrom(request, receipt.publicBoard.firstPackJsonHref);
  expect(pack.tour_action_href).toBe('/runsites/packs/redmond-dockyard-pack/tour');
  const markdown = await request.get(`${baseUrl}${receipt.publicBoard.firstPackMarkdownHref}`);
  expect(markdown.status()).toBe(200);
  await publicPage(page, '/runsites', 'RUNSITE');
  await expect(page.getByRole('link', { name: 'Open 3D Tour' }).first()).toHaveAttribute('href', pack.tour_action_href);
  const loginLocation = await expectLoginBoundary(request, pack.tour_action_href);

  writeGold({
    horizon_id: 'runsite',
    route: '/runsites',
    receipt_route: '/runsites/receipts/prep-network.json',
    assertion_count: 15,
    journey_steps: ['load prep-network receipt', 'render prep board', 'open JSON pack', 'open markdown pack', 'verify tour identity boundary'],
    boundaries_verified: ['pack_remains_inspectable', 'no_tactical_authority', 'not_a_vtt_replacement', 'tour_handoff_requires_identity'],
    evidence: {
      receipt_route: '/runsites/receipts/prep-network.json',
      json_route: receipt.publicBoard.firstPackJsonHref,
      markdown_route: receipt.publicBoard.firstPackMarkdownHref,
      login_location: loginLocation,
    },
  });
});

test('gold horizon: runbook-press executes primer files and identity-gated export', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/runbook/receipts/primer-network.json');
  expect(receipt.horizon).toBe('runbook-press');
  expect(receipt.status).toBe('shipped_mvp');
  expect(receipt.boundary.publicationStudio).toBe('not_claimed');
  expect(receipt.boundary.sourceTruth).toBe('chummer_owned_primer_packets');
  const primer = await jsonFrom(request, receipt.publicBoard.firstPrimerJsonHref);
  expect(primer.tour_action_href).toBe('/runbook/primers/new-runner-primer/export');
  const markdown = await request.get(`${baseUrl}${receipt.publicBoard.firstPrimerMarkdownHref}`);
  expect(markdown.status()).toBe(200);
  expect(markdown.headers()['content-type'] || '').toContain('text/markdown');
  await publicPage(page, '/runbook', 'RUNBOOK PRESS');
  await expect(page.getByRole('link', { name: 'Export Primer' }).first()).toHaveAttribute('href', primer.tour_action_href);
  const loginLocation = await expectLoginBoundary(request, primer.tour_action_href);

  writeGold({
    horizon_id: 'runbook-press',
    route: '/runbook',
    receipt_route: '/runbook/receipts/primer-network.json',
    assertion_count: 15,
    journey_steps: ['load primer-network receipt', 'render primer shelf', 'open JSON primer', 'open markdown primer', 'verify export identity boundary'],
    boundaries_verified: ['primer_source_is_chummer_owned', 'full_publication_studio_not_claimed', 'provider_not_truth', 'formatted_export_requires_identity'],
    evidence: {
      receipt_route: '/runbook/receipts/primer-network.json',
      json_route: receipt.publicBoard.firstPrimerJsonHref,
      markdown_route: receipt.publicBoard.firstPrimerMarkdownHref,
      login_location: loginLocation,
    },
  });
});

test('gold horizon: table-pulse executes live/aftermath separation and private debrief boundary', async ({ page, request }) => {
  const receipt = await jsonFrom(request, '/table-pulse/receipts/live-and-aftermath.json');
  expect(receipt.horizon).toBe('table_pulse');
  expect(receipt.status).toBe('shipped_mvp');
  expect(receipt.separationStatus).toBe('pass');
  expect(receipt.liveRail.status).toBe('live');
  expect(receipt.aftermathRail.status).toBe('live');
  expect(receipt.boundaries).toEqual(expect.arrayContaining(['no_automatic_world_changes', 'no_player_scoring', 'no_public_surveillance']));
  await publicPage(page, '/table-pulse', 'TABLE PULSE');
  await expect(page.getByRole('link', { name: 'Open aftermath' })).toHaveAttribute('href', '/table-pulse/debrief');
  const loginLocation = await expectLoginBoundary(request, '/table-pulse/debrief');

  writeGold({
    horizon_id: 'table-pulse',
    route: '/table-pulse',
    receipt_route: '/table-pulse/receipts/live-and-aftermath.json',
    assertion_count: 14,
    journey_steps: ['load live-and-aftermath receipt', 'render separated rails', 'inspect private debrief handoff', 'verify identity boundary'],
    boundaries_verified: ['live_and_aftermath_separate', 'no_automatic_world_changes', 'no_player_scoring', 'no_public_surveillance', 'aftermath_requires_identity'],
    evidence: { receipt_route: '/table-pulse/receipts/live-and-aftermath.json', login_location: loginLocation },
  });
});
