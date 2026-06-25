import { createHash } from 'node:crypto';
import { expect, request, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

type AurPackageEntry = {
  id: string;
  packageName: string;
  packageVersion: string;
  title: string;
  sourceArchiveUrl: string;
  sourceArchiveSha256: string;
  pkgbuildUrl: string;
  pkgbuildSha256: string;
  srcinfoUrl: string;
  srcinfoSha256: string;
  upstreamArtifactUrl: string;
  upstreamArtifactSha256: string;
};

function sha256(buffer: Buffer): string {
  return createHash('sha256').update(buffer).digest('hex');
}

test('downloads publishes the Arch-compatible AUR sidecar for the current Linux build', async ({ page }) => {
  test.setTimeout(120000);
  const api = await request.newContext({ baseURL: baseUrl });
  const checks: Array<Record<string, unknown>> = [];

  await page.goto(`${baseUrl}/downloads`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Downloads' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Build from source' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Download script' })).toBeVisible();

  const catalogResponse = await api.get('/downloads/aur-packages.json');
  expect(catalogResponse.status()).toBe(200);
  const catalog = await catalogResponse.json() as { packages?: AurPackageEntry[] };
  expect(catalog.packages?.length).toBeGreaterThan(0);

  const aurPackage = catalog.packages!.find((entry) => entry.id === 'chummer6-bin');
  expect(aurPackage, 'chummer6-bin package should exist in the AUR catalog').toBeTruthy();
  expect(aurPackage!.packageVersion).toMatch(/^\d{8}\.\d{6}$/);
  expect(aurPackage!.upstreamArtifactSha256).toMatch(/^[a-f0-9]{64}$/);

  for (const [label, url, expectedHash] of [
    ['source archive', aurPackage!.sourceArchiveUrl, aurPackage!.sourceArchiveSha256],
    ['PKGBUILD', aurPackage!.pkgbuildUrl, aurPackage!.pkgbuildSha256],
    ['SRCINFO', aurPackage!.srcinfoUrl, aurPackage!.srcinfoSha256],
  ] as const) {
    const response = await api.get(new URL(url).pathname);
    expect(response.status(), `${label} should download`).toBe(200);
    const body = await response.body();
    expect(body.length, `${label} should not be empty`).toBeGreaterThan(64);
    expect(sha256(body), `${label} hash should match catalog`).toBe(expectedHash);
    checks.push({ label, bytes: body.length, sha256: expectedHash });
  }

  const pkgbuild = await (await api.get(new URL(aurPackage!.pkgbuildUrl).pathname)).text();
  expect(pkgbuild).toContain('pkgname=chummer6-bin');
  expect(pkgbuild).toContain(`pkgver=${aurPackage!.packageVersion}`);
  expect(pkgbuild).toContain(aurPackage!.upstreamArtifactUrl);
  expect(pkgbuild).toContain(aurPackage!.upstreamArtifactSha256);

  writeJsonArtifact('DOWNLOADS_AUR_SIDECAR_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    base_url: baseUrl,
    status: 'pass',
    package: aurPackage,
    checks,
  });
});
