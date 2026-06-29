import { expect, request, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

const routes = [
  '/',
  '/downloads',
  '/status',
  '/help',
  '/contact',
  '/participate',
  '/participate/board',
  '/roadmap',
  '/changelog',
  '/account/billing',
  '/api/health',
];

test('public route health checks accept HEAD without returning method-not-allowed', async () => {
  test.setTimeout(90000);
  const api = await request.newContext();
  const rows: Array<{ route: string; status: number; location: string | null }> = [];

  for (const route of routes) {
    const response = await api.fetch(`${baseUrl}${route}`, {
      method: 'HEAD',
      maxRedirects: 0,
    });
    const status = response.status();
    const location = response.headers()['location'] ?? null;
    rows.push({ route, status, location });

    expect(status, `${route} should not reject HEAD`).not.toBe(405);
    expect(status, `${route} should be alive or intentionally redirect`).toBeLessThan(500);
  }

  writeJsonArtifact('PUBLIC_HEAD_REQUESTS.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    rows,
  });
});
