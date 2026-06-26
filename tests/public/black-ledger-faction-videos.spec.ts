import { test, expect } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';
const factions = [
  'glass-tower-compact',
  'rust-market-syndicate',
  'ashline-circle',
  'neon-docks-union',
  'ghostline-network',
  'barrens-free-wardens',
];

test('black ledger faction promo routes stay public-safe and keep vendor truth out of public metadata', async ({ request }) => {
  test.setTimeout(90000);
  const results: Array<Record<string, unknown>> = [];
  for (const faction of factions) {
    const [page, json, vtt] = await Promise.all([
      request.get(`${baseUrl}/ledger/factions/${faction}/promo`),
      request.get(`${baseUrl}/ledger/factions/${faction}/promo.json`),
      request.get(`${baseUrl}/ledger/factions/${faction}/promo.vtt`),
    ]);
    const pageText = await page.text();
    const payload = await json.json();
    expect(page.status()).toBe(200);
    expect(json.status()).toBe(200);
    expect(vtt.status()).toBe(200);
    expect(typeof payload.provider_status).toBe('string');
    expect(typeof payload.render_mode).toBe('string');
    expect(payload.provider_status).toBe('VERIFIED_PROVIDER');
    expect(payload.render_mode).toBe('verified_cinematic_faction_bulletin');
    expect(payload.fallback_render_mode).toBe('storyboard_fallback');
    expect(typeof payload.storyline_summary).toBe('string');
    expect(typeof payload.narrator_posture).toBe('string');
    expect(typeof payload.render_pipeline).toBe('string');
    expect(typeof payload.video_mp4_href).toBe('string');
    expect(typeof payload.video_webm_href).toBe('string');
    expect(typeof payload.poster_href).toBe('string');
    expect(typeof payload.campaign_hook).toBe('string');
    expect(typeof payload.audience_promise).toBe('string');
    expect(typeof payload.validation_href).toBe('string');
    expect(Array.isArray(payload.storyboard_shots)).toBeTruthy();
    expect(payload.storyboard_shots.length).toBeGreaterThanOrEqual(3);
    expect(Array.isArray(payload.screenplay_scenes)).toBeTruthy();
    expect(payload.screenplay_scenes.length).toBeGreaterThanOrEqual(3);
    expect(pageText).toContain('<video');
    expect(JSON.stringify(payload)).not.toContain('MagicFit');
    expect(pageText).not.toContain('MagicFit');
    const protectedVideoUrl = new URL(payload.video_mp4_href, baseUrl);
    expect(protectedVideoUrl.searchParams.get('artifactAccess')).toBeTruthy();
    const rawVideoResponse = await request.get(`${protectedVideoUrl.origin}${protectedVideoUrl.pathname}`);
    expect(rawVideoResponse.status()).toBe(404);
    results.push({
      faction,
      page: page.status(),
      json: json.status(),
      vtt: vtt.status(),
      provider_status: payload.provider_status,
      render_mode: payload.render_mode,
      fallback_render_mode: payload.fallback_render_mode,
      narrator_posture: payload.narrator_posture,
      validation_href: payload.validation_href,
      video_mp4_href: payload.video_mp4_href,
      storyboard_shot_count: payload.storyboard_shots.length,
    });
  }

  writeJsonArtifact('BLACK_LEDGER_FACTION_VIDEO_CARD_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    results,
  });
});
