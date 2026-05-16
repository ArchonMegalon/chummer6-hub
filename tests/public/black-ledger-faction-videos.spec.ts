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

test('black ledger faction promo routes stay public-safe and fallback-backed', async ({ request }) => {
  const results: Array<Record<string, unknown>> = [];
  for (const faction of factions) {
    const page = await request.get(`${baseUrl}/ledger/factions/${faction}/promo`);
    const json = await request.get(`${baseUrl}/ledger/factions/${faction}/promo.json`);
    const vtt = await request.get(`${baseUrl}/ledger/factions/${faction}/promo.vtt`);
    const payload = await json.json();
    expect(page.status()).toBe(200);
    expect(json.status()).toBe(200);
    expect(vtt.status()).toBe(200);
    expect(payload.provider_status).toBe('NEEDS_PROVIDER_VERIFICATION');
    expect(payload.render_mode).toBe('fallback_static_storyboard');
    results.push({ faction, page: page.status(), json: json.status(), vtt: vtt.status(), provider_status: payload.provider_status, render_mode: payload.render_mode });
  }

  writeJsonArtifact('BLACK_LEDGER_FACTION_VIDEO_CARD_PROOF.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    results,
  });
});
