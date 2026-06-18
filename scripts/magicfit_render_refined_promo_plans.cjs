const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 ? process.argv[idx + 1] : null;
}

const MANIFEST = argValue('--manifest') || '/docker/chummercomplete/_completion/refined_magicfit_promo_plans_20260531/REFINED_MAGICFIT_RENDER_MANIFEST.generated.json';
const OUT_ROOT = argValue('--out-root') || '/docker/chummercomplete/_completion/refined_magicfit_promo_plans_20260531/magicfit_clips';
const ENV_FILES = [
  '/docker/chummercomplete/chummer.run-services/.env',
  '/docker/EA/.env',
];

function loadEnv(file, override = false) {
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
    if (override || !(key in process.env)) process.env[key] = value;
  }
}
for (const file of ENV_FILES) loadEnv(file);

const overrideEnvFile = argValue('--env-file');
if (overrideEnvFile) loadEnv(overrideEnvFile, true);

function accountLabel() {
  return argValue('--account-label') || (overrideEnvFile ? safeName(path.basename(path.dirname(overrideEnvFile)) || path.basename(overrideEnvFile)) : 'default');
}

function safeName(value) {
  return String(value).replace(/[^a-zA-Z0-9_.-]+/g, '_');
}

function clipDir(asset) {
  return path.join(OUT_ROOT, safeName(asset.asset_id));
}

function scenePath(asset, scene, suffix) {
  return path.join(clipDir(asset), `${safeName(scene.id)}${suffix}`);
}

async function login(page) {
  await page.goto('https://magicfit.pushowl.com/home', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(4000);
  const body = await page.locator('body').innerText({ timeout: 10000 }).catch(() => '');
  if (!/login|sign in|email|password/i.test(body)) return;
  const email = process.env.CHUMMER_EA_MAGICFIT_EMAIL || process.env.MAGICFIT_EMAIL || '';
  const password = process.env.CHUMMER_EA_MAGICFIT_PASSWORD || process.env.MAGICFIT_PASSWORD || '';
  if (!email || !password) throw new Error('MagicFit credentials are missing from env.');
  const emailField = page.locator('input[type=email], input[name*=email i], input[placeholder*=email i]').first();
  if (await emailField.count()) await emailField.fill(email);
  const passwordField = page.locator('input[type=password]').first();
  if (await passwordField.count()) await passwordField.fill(password);
  const submit = page.getByRole('button', { name: /sign in|login|continue|submit/i }).first();
  if (await submit.count()) await submit.click();
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForTimeout(8000);
}

async function selectPill(page, currentText, optionText) {
  const pill = page.getByRole('button', { name: currentText }).last();
  await pill.click({ timeout: 10000 });
  await page.waitForTimeout(500);
  const option = page.getByText(optionText, { exact: true }).last();
  await option.click({ timeout: 10000 });
  await page.waitForTimeout(500);
}

async function fillPrompt(page, prompt) {
  const box = page.locator('[contenteditable="true"][role="textbox"]').first();
  await box.click({ timeout: 10000 }).catch(async () => {
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(500);
    await box.click({ timeout: 10000, force: true });
  });
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A').catch(() => {});
  await page.keyboard.insertText(prompt).catch(async () => {
    await box.evaluate((node, value) => {
      node.textContent = value;
      node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
    }, prompt);
  });
  await page.waitForTimeout(800);
}

async function clickGenerate(page) {
  const buttonIndex = await page.locator('button').evaluateAll((nodes) => {
    const candidates = nodes
      .map((node, index) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        const text = (node.innerText || node.textContent || '').trim();
        return {
          index,
          text,
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
          disabled: node.disabled || node.getAttribute('aria-disabled') === 'true',
          visible: rect.width > 20 && rect.height > 20 && style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity || '1') > 0.2,
          background: style.backgroundColor || '',
        };
      })
      .filter((item) => item.visible && !item.disabled)
      .filter((item) => item.text.length <= 2 || /^[+x×-]?\d*$/.test(item.text))
      .sort((left, right) => {
        const leftGreen = /rgb\((?:1[0-9]{2}|[89][0-9]),\s*(?:1[3-9][0-9]|2[0-5][0-9]),/.test(left.background) ? 1 : 0;
        const rightGreen = /rgb\((?:1[0-9]{2}|[89][0-9]),\s*(?:1[3-9][0-9]|2[0-5][0-9]),/.test(right.background) ? 1 : 0;
        return rightGreen - leftGreen || right.bottom - left.bottom || right.right - left.right;
      });
    return candidates[0]?.index ?? -1;
  });
  if (buttonIndex < 0) throw new Error('Unable to locate MagicFit generate button');
  const button = page.locator('button').nth(buttonIndex);
  await button.scrollIntoViewIfNeeded().catch(() => {});
  await button.click({ timeout: 30000, force: true });
}

function download(url, file) {
  return new Promise((resolve, reject) => {
    const out = fs.createWriteStream(file);
    https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        out.close();
        fs.unlinkSync(file);
        return download(res.headers.location, file).then(resolve, reject);
      }
      if (res.statusCode !== 200) {
        out.close();
        fs.unlinkSync(file);
        reject(new Error(`download ${url} failed with ${res.statusCode}`));
        return;
      }
      res.pipe(out);
      out.on('finish', () => out.close(resolve));
    }).on('error', (error) => {
      out.close();
      try { fs.unlinkSync(file); } catch {}
      reject(error);
    });
  });
}

function collectCdnVideoUrlsFromText(text) {
  return [...new Set((text.match(/https:\/\/(?:cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/[^"'\s<>]+?\.(?:mp4|webm)(?:[^"'\s<>]*)?/g) || [])
    .map((url) => url.replace(/\\u0026/g, '&').replace(/[),\]]+$/, '')))];
}

function magicfitUrlTimestamp(url) {
  const match = url.match(/\/magicfit\/(\d+)-/);
  return match ? Number(match[1]) : 0;
}

async function collectVisibleMagicFitVideoUrls(page) {
  const urls = new Set();
  const html = await page.content().catch(() => '');
  for (const found of collectCdnVideoUrlsFromText(html)) urls.add(found);
  const videos = await page.locator('video').evaluateAll((nodes) => nodes.map((v) => v.currentSrc || v.src).filter(Boolean)).catch(() => []);
  for (const found of videos) {
    if (/(cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/.*\.(mp4|webm)/.test(found)) urls.add(found);
  }
  return urls;
}

function chooseNewestVideoUrl(urls, baseline, submittedAtMs) {
  const candidates = [...urls]
    .filter((url) => /\.(mp4|webm)(?:$|\?)/.test(url))
    .filter((url) => !baseline.has(url))
    .map((url) => ({ url, timestamp: magicfitUrlTimestamp(url) }))
    .filter((item) => item.timestamp === 0 || item.timestamp >= submittedAtMs - 120000)
    .sort((left, right) => right.timestamp - left.timestamp);
  return candidates[0]?.url || null;
}

async function renderScene(page, asset, scene) {
  fs.mkdirSync(clipDir(asset), { recursive: true });
  const mp4Path = scenePath(asset, scene, '.mp4');
  const sidecarPath = scenePath(asset, scene, '.magicfit.json');
  if (fs.existsSync(mp4Path) && fs.existsSync(sidecarPath) && !process.argv.includes('--force')) {
    console.log(`skip ${asset.asset_id}/${scene.id}`);
    return;
  }

  const events = [];
  const seenVideoUrls = new Set();
  const responseHandler = async (response) => {
    const url = response.url();
    if (!url.includes('magicfit') && !url.includes('pushowl')) return;
    const item = { status: response.status(), url, contentType: response.headers()['content-type'] || '' };
    events.push(item);
    if (/(cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/.*\.(mp4|webm)(?:$|\?)/.test(url)) seenVideoUrls.add(url);
    if (/json|script|text/.test(item.contentType)) {
      const text = await response.text().catch(() => '');
      for (const found of collectCdnVideoUrlsFromText(text)) seenVideoUrls.add(found);
    }
  };
  page.on('response', responseHandler);

  try {
    await page.goto('https://magicfit.pushowl.com/agents/generate?mode=video', { waitUntil: 'domcontentloaded', timeout: 120000 });
    await page.waitForTimeout(5000);
    const baselineVideoUrls = await collectVisibleMagicFitVideoUrls(page);
    await selectPill(page, '9:16', 'Landscape (16:9)').catch(async () => {
      await page.locator('select').nth(0).selectOption('16:9').catch(() => {});
    });
    await selectPill(page, '4s', `${scene.duration_seconds}s`).catch(async () => {
      await page.locator('select').nth(1).selectOption(String(scene.duration_seconds)).catch(() => {});
    });
    const fullPrompt = `${scene.prompt} Negative constraints: ${scene.negative_prompt || ''}`;
    await fillPrompt(page, fullPrompt);
    await page.screenshot({ path: scenePath(asset, scene, '.before-submit.png'), fullPage: true });
    const submittedAtMs = Date.now();
    await clickGenerate(page);
    console.log(`submitted ${asset.asset_id}/${scene.id}`);
    await page.waitForTimeout(3000);

    const timeoutMinutes = Number(argValue('--timeout-minutes') || '18');
    const deadline = Date.now() + timeoutMinutes * 60 * 1000;
    let videoUrl = null;
    while (Date.now() < deadline && !videoUrl) {
      await page.waitForTimeout(10000);
      const html = await page.content().catch(() => '');
      for (const found of collectCdnVideoUrlsFromText(html)) seenVideoUrls.add(found);
      const videos = await page.locator('video').evaluateAll((nodes) => nodes.map((v) => v.currentSrc || v.src).filter(Boolean)).catch(() => []);
      for (const found of videos) {
        if (/(cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/.*\.(mp4|webm)/.test(found)) seenVideoUrls.add(found);
      }
      videoUrl = chooseNewestVideoUrl(seenVideoUrls, baselineVideoUrls, submittedAtMs);
      if (!videoUrl) console.log(`poll ${asset.asset_id}/${scene.id}: waiting`);
    }
    await page.screenshot({ path: scenePath(asset, scene, '.after-render.png'), fullPage: true }).catch(() => {});
    if (!videoUrl) {
      fs.writeFileSync(scenePath(asset, scene, '.failed.json'), JSON.stringify({ asset, scene, events: events.slice(-200), url: page.url() }, null, 2));
      throw new Error(`No MagicFit video URL found for ${asset.asset_id}/${scene.id}`);
    }
    await download(videoUrl, mp4Path);
    fs.writeFileSync(sidecarPath, JSON.stringify({
      provider: 'MagicFit',
      rendered_by: 'EA MagicFit browser automation',
      account_label: accountLabel(),
      lane: asset.lane,
      asset_id: asset.asset_id,
      horizon: asset.horizon,
      scene_id: scene.id,
      scene_number: scene.scene_number,
      title: scene.title,
      duration_seconds_requested: scene.duration_seconds,
      aspect_ratio: '16:9',
      resolution: '720p',
      model: 'Seedance 2.0 Fast',
      video_output_url: videoUrl,
      source_prompt: fullPrompt,
      official_ip_assets_used: false,
      direct_publish: false,
      generated_at_utc: new Date().toISOString(),
      page_url_after_submit: page.url(),
      event_tail: events.slice(-80),
    }, null, 2));
    console.log(`rendered ${asset.asset_id}/${scene.id} -> ${mp4Path}`);
  } finally {
    page.off('response', responseHandler);
  }
}

function selectWork(manifest) {
  const lane = argValue('--lane');
  const assetId = argValue('--asset');
  const only = argValue('--only');
  const maxScenes = Number(argValue('--max-scenes') || '0');
  const shard = argValue('--shard');
  const onlySet = only ? new Set(only.split(',').map((s) => s.trim())) : null;
  const pairs = [];
  for (const asset of manifest.assets) {
    if (lane && asset.lane !== lane) continue;
    if (assetId && asset.asset_id !== assetId) continue;
    for (const scene of asset.scenes) {
      if (onlySet && !onlySet.has(scene.id) && !onlySet.has(String(scene.scene_number).padStart(2, '0'))) continue;
      pairs.push({ asset, scene });
    }
  }
  let selected = pairs;
  if (shard) {
    const match = shard.match(/^(\d+)\/(\d+)$/);
    if (!match) throw new Error('--shard must use zero-based INDEX/TOTAL, for example 0/2');
    const index = Number(match[1]);
    const total = Number(match[2]);
    if (!Number.isInteger(index) || !Number.isInteger(total) || total < 1 || index < 0 || index >= total) {
      throw new Error('--shard index must be zero-based and less than total');
    }
    selected = pairs.filter((_, position) => position % total === index);
  }
  return maxScenes > 0 ? selected.slice(0, maxScenes) : selected;
}

async function main() {
  const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
  const work = selectWork(manifest);
  if (!work.length) throw new Error('No scenes selected.');
  console.log(`selected ${work.length} scene(s) account=${accountLabel()}`);
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
  const page = await context.newPage();
  await login(page);
  for (const { asset, scene } of work) {
    try {
      await renderScene(page, asset, scene);
    } catch (error) {
      if (!process.argv.includes('--continue-on-fail')) throw error;
      console.error(`failed ${asset.asset_id}/${scene.id}: ${error.message || error}`);
    }
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
