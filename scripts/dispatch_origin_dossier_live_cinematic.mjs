#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

function required(name) {
  const value = process.env[name]?.trim() || '';
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function nowIso() {
  return new Date().toISOString();
}

async function writeJson(target, payload) {
  if (!target) {
    return;
  }
  await mkdir(path.dirname(path.resolve(target)), { recursive: true });
  await writeFile(target, `${JSON.stringify(payload, null, 2)}\n`, { encoding: 'utf8', mode: 0o600 });
}

async function main() {
  if (process.env.CHUMMER_E2E_ALLOW_LIVE_MEDIA_DISPATCH?.trim() !== '1') {
    throw new Error('CHUMMER_E2E_ALLOW_LIVE_MEDIA_DISPATCH=1 is required because this operation can spend provider credits');
  }

  const baseUrl = required('BASE_URL').replace(/\/+$/, '');
  const projectId = required('CHUMMER_E2E_ORIGIN_DOSSIER_PROJECT_ID');
  const sceneId = required('CHUMMER_E2E_ORIGIN_DOSSIER_SCENE_ID');
  const identityToken = required('CHUMMER_E2E_IDENTITY_TOKEN');
  const cookieName = process.env.CHUMMER_E2E_COOKIE_NAME?.trim() || 'chummer_hub_access_token';
  const outputPath = process.env.CHUMMER_E2E_RECEIPT_PATH?.trim() || '';
  const screenshotPath = process.env.CHUMMER_E2E_SCREENSHOT_PATH?.trim() || '';
  const allowServerDispatch = process.env.CHUMMER_E2E_ALLOW_SERVER_DISPATCH?.trim() === '1';
  const hostResolverRules = process.env.CHUMMER_E2E_HOST_RESOLVER_RULES?.trim() || '';
  const parsedBaseUrl = new URL(baseUrl);
  const ownerUrl = `${baseUrl}/account/work/origin-dossiers/${encodeURIComponent(projectId)}`;
  const postPath = `/account/work/origin-dossiers/${encodeURIComponent(projectId)}/cinematic-scene`;
  const startedAtUtc = nowIso();
  const browserArgs = ['--disable-quic'];
  if (hostResolverRules) {
    browserArgs.push(`--host-resolver-rules=${hostResolverRules}`);
  }
  const browser = await chromium.launch({ headless: true, args: browserArgs });

  try {
    const context = await browser.newContext();
    await context.addCookies([
      {
        name: cookieName,
        value: identityToken,
        domain: parsedBaseUrl.hostname,
        path: '/',
        httpOnly: false,
        secure: parsedBaseUrl.protocol === 'https:',
        sameSite: 'Lax',
      },
    ]);
    const page = await context.newPage();
    const initialResponse = await page.goto(ownerUrl, { waitUntil: 'domcontentloaded', timeout: 90_000 });
    if (!initialResponse || initialResponse.status() !== 200) {
      throw new Error(`owner page returned ${initialResponse?.status() ?? 'no response'}`);
    }
    if (!(await page.locator('[data-origin-dossier-detail]').isVisible())) {
      throw new Error('owner page did not expose the Origin Dossier detail contract');
    }
    const sceneInput = page.locator(`form[action="${postPath}"] input[name="sceneId"][value="${sceneId}"]`);
    const buttonVisible = (await sceneInput.count()) === 1
      && await sceneInput.locator('..').getByRole('button', { name: 'Render this 2¼-minute chapter movie' }).isVisible();
    if (!buttonVisible && !allowServerDispatch) {
      throw new Error(`expected one visible render form for scene ${sceneId}`);
    }
    const responsePromise = page.waitForResponse(
      (response) => response.request().method() === 'POST' && new URL(response.url()).pathname === postPath,
      { timeout: 90_000 },
    );
    const navigationPromise = page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 90_000 });
    if (buttonVisible) {
      await sceneInput.locator('..').getByRole('button', { name: 'Render this 2¼-minute chapter movie' }).click();
    } else {
      const verificationToken = await page.locator('input[name="__RequestVerificationToken"]').first().inputValue();
      if (!verificationToken) {
        throw new Error('signed-in page did not expose an antiforgery token for the guarded server dispatch');
      }
      await page.evaluate(
        ({ action, selectedSceneId, token }) => {
          const form = document.createElement('form');
          form.method = 'post';
          form.action = action;
          for (const [name, value] of Object.entries({
            sceneId: selectedSceneId,
            __RequestVerificationToken: token,
          })) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = value;
            form.append(input);
          }
          document.body.append(form);
          form.submit();
        },
        { action: postPath, selectedSceneId: sceneId, token: verificationToken },
      );
    }
    const dispatchResponse = await responsePromise;
    if (![302, 303].includes(dispatchResponse.status())) {
      throw new Error(`chapter movie dispatch returned ${dispatchResponse.status()}`);
    }
    await navigationPromise;
    await page.locator('[data-origin-dossier-detail]').waitFor({ state: 'visible', timeout: 90_000 });
    let selectionPersisted = false;
    const selectedRow = page.locator('.settings-summary-row', { hasText: 'Clinic Door in the Rain' });
    if ((await selectedRow.count()) === 1) {
      selectionPersisted = await selectedRow.getByText('Selected', { exact: true }).isVisible();
      if (!selectionPersisted) {
        throw new Error('selected chapter scene was not persisted after dispatch');
      }
    }
    if (screenshotPath) {
      await mkdir(path.dirname(path.resolve(screenshotPath)), { recursive: true });
      await page.screenshot({ path: screenshotPath, fullPage: true });
    }

    const requestId = dispatchResponse.headers()['x-origin-dossier-media-request-id'] || '';
    if (!requestId) {
      throw new Error('dispatch response omitted X-Origin-Dossier-Media-Request-Id');
    }
    const receipt = {
      contractName: 'chummer.origin_dossier.live_cinematic_dispatch.browser_receipt.v1',
      status: 'pass',
      startedAtUtc,
      completedAtUtc: nowIso(),
      baseUrl,
      projectId,
      sceneId,
      ownerUrl,
      requestId,
      requestIdSha256: sha256(requestId),
      buttonLabel: 'Render this 2¼-minute chapter movie',
      uiButtonVisible: buttonVisible,
      browserButtonClicked: buttonVisible,
      authenticatedCsrfFormSubmitted: !buttonVisible,
      customHostResolverUsed: Boolean(hostResolverRules),
      selectionPersistedInRenderedUi: selectionPersisted,
      rawSessionTokenStored: false,
      providerCreditsMayBeConsumed: true,
      screenshotPath: screenshotPath || null,
    };
    await writeJson(outputPath, receipt);
    process.stdout.write(`${JSON.stringify(receipt)}\n`);
    await context.close();
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
