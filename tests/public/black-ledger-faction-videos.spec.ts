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

test('black ledger faction promo routes stay public-safe and first-party-video-backed', async ({ request }) => {
  const results: Array<Record<string, unknown>> = [];
  for (const faction of factions) {
    const page = await request.get(`${baseUrl}/ledger/factions/${faction}/promo`);
    const json = await request.get(`${baseUrl}/ledger/factions/${faction}/promo.json`);
    const vtt = await request.get(`${baseUrl}/ledger/factions/${faction}/promo.vtt`);
    const pageText = await page.text();
    const payload = await json.json();
    expect(page.status()).toBe(200);
    expect(json.status()).toBe(200);
    expect(vtt.status()).toBe(200);
    expect(payload.provider_status).toBe('FIRST_PARTY_VIDEO');
    expect(payload.render_mode).toBe('first_party_motion_video');
    expect(payload.fallback_render_mode).toBe('first_party_storyboard');
    expect(typeof payload.video_mp4_href).toBe('string');
    expect(typeof payload.video_webm_href).toBe('string');
    expect(typeof payload.poster_href).toBe('string');
    expect(typeof payload.campaign_hook).toBe('string');
    expect(typeof payload.audience_promise).toBe('string');
    expect(typeof payload.validation_href).toBe('string');
    expect(Array.isArray(payload.storyboard_shots)).toBeTruthy();
    expect(payload.storyboard_shots.length).toBeGreaterThanOrEqual(3);
    expect(pageText).toContain('<video');
    results.push({
      faction,
      page: page.status(),
      json: json.status(),
      vtt: vtt.status(),
      provider_status: payload.provider_status,
      render_mode: payload.render_mode,
      fallback_render_mode: payload.fallback_render_mode,
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
