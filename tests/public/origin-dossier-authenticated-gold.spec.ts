import { expect, request as playwrightRequest, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = (process.env.BASE_URL?.trim() || 'http://127.0.0.1:8091').replace(/\/+$/, '');
const identityToken = process.env.CHUMMER_E2E_IDENTITY_TOKEN?.trim() || '';
const projectId = process.env.CHUMMER_E2E_ORIGIN_DOSSIER_PROJECT_ID?.trim() || 'origin-browser';

test('signed-in owner can see Origin Dossier cover, tabs, and gated media links through chummer.run', async ({ browser }) => {
  test.setTimeout(90_000);
  test.skip(!identityToken, 'Origin Dossier authenticated proof needs CHUMMER_E2E_IDENTITY_TOKEN.');

  const parsedBaseUrl = new URL(baseUrl);
  const context = await browser.newContext();
  await context.addCookies([
    {
      name: 'chummer_hub_access_token',
      value: identityToken,
      domain: parsedBaseUrl.hostname,
      path: '/',
      httpOnly: false,
      secure: parsedBaseUrl.protocol === 'https:',
      sameSite: 'Lax',
    },
  ]);
  const page = await context.newPage();

  await page.goto(`${baseUrl}/account/work#origin-dossier-library`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#origin-dossier-library')).toBeVisible();
  await expect(page.locator('#origin-dossier-library')).toContainText('Route Runner Origin Dossier');
  await expect(page.locator('#origin-dossier-library')).toContainText('Gold ready');
  await expect(page.getByRole('link', { name: 'Listen in Audiobookshelf' })).toHaveAttribute(
    'href',
    `${baseUrl}/account/work/origin-dossiers/${projectId}/listen`,
  );

  await page.getByRole('link', { name: 'Open authenticated chummer.run edition' }).click();
  await expect(page).toHaveURL(`${baseUrl}/account/work/origin-dossiers/${projectId}`);
  await expect(page.locator('[data-origin-dossier-detail]')).toBeVisible();
  await expect(page.locator('[data-origin-dossier-gold-ready="true"]')).toBeVisible();
  await expect(page.locator('[data-story-scene-cover-uses-selected-character-face="true"]')).toBeVisible();
  await expect(page.locator('[data-origin-edition-tab="read"]')).toBeVisible();
  await expect(page.locator('[data-origin-edition-tab="listen"]')).toBeVisible();
  await expect(page.locator('[data-origin-edition-tab="watch"]')).toBeVisible();
  await expect(page.locator('[data-origin-edition-tab="canon-audit"]')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Read' })).toHaveAttribute('href', '#origin-edition-read');
  await expect(page.getByRole('link', { name: 'Listen' })).toHaveAttribute('href', '#origin-edition-listen');
  await expect(page.getByRole('link', { name: 'Watch' })).toHaveAttribute('href', '#origin-edition-watch');
  await expect(page.getByRole('link', { name: 'Canon Audit' })).toHaveAttribute('href', '#origin-edition-canon-audit');
  const coverImage = page.getByAltText('Rendered Origin Dossier story scene cover for Route Runner');
  await expect(coverImage).toHaveAttribute('src', `${baseUrl}/account/work/origin-dossiers/${projectId}/cover`);
  await expect(page.getByRole('link', { name: 'Read in Audiobookshelf' })).toHaveAttribute(
    'href',
    `${baseUrl}/account/work/origin-dossiers/${projectId}/read`,
  );
  await expect(page.getByRole('link', { name: 'Open archived book' })).toHaveAttribute(
    'href',
    `${baseUrl}/account/work/origin-dossiers/${projectId}/book`,
  );
  await expect(page.getByRole('link', { name: 'Listen in Audiobookshelf' })).toHaveAttribute(
    'href',
    `${baseUrl}/account/work/origin-dossiers/${projectId}/listen`,
  );
  await expect(page.getByRole('link', { name: 'Watch scene movie' })).toHaveAttribute(
    'href',
    `${baseUrl}/account/work/origin-dossiers/${projectId}/video`,
  );

  const unauthenticatedRequest = await playwrightRequest.newContext({ baseURL: baseUrl });
  const unauthenticatedDetail = await unauthenticatedRequest.get(`/account/work/origin-dossiers/${projectId}`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(unauthenticatedDetail.status());
  expect(unauthenticatedDetail.headers()['location']).toContain('/login?next=');
  const unauthenticatedBook = await unauthenticatedRequest.get(`/account/work/origin-dossiers/${projectId}/book`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(unauthenticatedBook.status());
  expect(unauthenticatedBook.headers()['location']).toContain('/login?next=');
  await unauthenticatedRequest.dispose();

  const cookieHeader = (await context.cookies())
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join('; ');
  const signedInRequest = await playwrightRequest.newContext({
    baseURL: baseUrl,
    extraHTTPHeaders: {
      Cookie: cookieHeader,
    },
  });
  const cover = await signedInRequest.get(`/account/work/origin-dossiers/${projectId}/cover`, { maxRedirects: 0 });
  expect(cover.status()).toBe(200);
  expect(cover.headers()['content-type']).toContain('image/png');

  const read = await signedInRequest.get(`/account/work/origin-dossiers/${projectId}/read`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(read.status());
  expect(read.headers()['location']).toBe(`https://audio.chummer.run/share/${projectId}-dossier`);

  const listen = await signedInRequest.get(`/account/work/origin-dossiers/${projectId}/listen`, { maxRedirects: 0 });
  expect([302, 303, 307, 308]).toContain(listen.status());
  expect(listen.headers()['location']).toBe(`https://audio.chummer.run/share/${projectId}`);

  const video = await signedInRequest.get(`/account/work/origin-dossiers/${projectId}/video`, { maxRedirects: 0 });
  expect(video.status()).toBe(200);
  expect(video.headers()['content-type']).toContain('video/mp4');

  await signedInRequest.dispose();
  await context.close();

  writeJsonArtifact('ORIGIN_DOSSIER_AUTHENTICATED_GOLD_E2E.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    proof_scope: 'authenticated_chummer_run_route_proof',
    local_fixture_artifacts: true,
    live_provider_artifacts_verified: false,
    live_provider_delivery_verified: false,
    remaining_live_requirements: [
      'provider-authored final story from Inkfluence, Youbooks, or First Book AI',
      'Undetectable Humanizer post-processing receipt from the live provider flow',
      'rendered story-scene cover using the selected character face',
      'real Inkfluence or Unmixr audiobook artifact imported into Audiobookshelf',
      'real dossier video artifact',
      'live Telegram delivery receipt',
      'owner opens the deployed chummer.run route and plays the live Audiobookshelf share',
    ],
    base_url: baseUrl,
    project_id: projectId,
    owner_account_page: `${baseUrl}/account/work#origin-dossier-library`,
    owner_detail_page: `${baseUrl}/account/work/origin-dossiers/${projectId}`,
    selected_face_cover_url: `${baseUrl}/account/work/origin-dossiers/${projectId}/cover`,
    read_url: `${baseUrl}/account/work/origin-dossiers/${projectId}/read`,
    book_url: `${baseUrl}/account/work/origin-dossiers/${projectId}/book`,
    listen_url: `${baseUrl}/account/work/origin-dossiers/${projectId}/listen`,
    watch_url: `${baseUrl}/account/work/origin-dossiers/${projectId}/video`,
    audiobookshelf_redirect: `https://audio.chummer.run/share/${projectId}`,
    logged_in_browser_verified: true,
    selected_face_cover_visible: true,
    read_tab_visible: true,
    listen_tab_visible: true,
    watch_tab_visible: true,
    canon_audit_tab_visible: true,
    read_gate_verified: true,
    chummer_run_listen_gate_verified: true,
    watch_gate_verified: true,
    unauthenticated_detail_redirect_verified: true,
    unauthenticated_artifact_redirect_verified: true,
  });
});
