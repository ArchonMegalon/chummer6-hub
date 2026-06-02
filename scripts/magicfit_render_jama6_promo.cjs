const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

const OUT_DIR = '/docker/chummercomplete/_completion/magicfit_jama6_promo_12_scenes';
const ENV_FILES = [
  '/docker/chummercomplete/chummer.run-services/.env',
  '/docker/EA/.env',
];

function loadEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = value;
  }
}

for (const file of ENV_FILES) loadEnv(file);

const GLOBAL_NEGATIVE = [
  'no factions',
  'no faction logos',
  'no faction recruitment ads',
  'no Shadowrun sourcebook text',
  'no copied rulebook pages',
  'no flat vector graphics',
  'no corporate SaaS explainer look',
  'no cartoon',
  'no animation',
  'no animated movie',
  'no 3d cartoon',
  'no toy figures',
  'no Lego',
  'no plastic figurines',
  'no children show style',
  'no mascot characters',
  'no bobblehead proportions',
  'no unreadable UI text',
  'no product name text',
  'no generated logos',
  'no title card text',
  'no misspelled interface labels',
  'no watermark',
].join(', ');

const SCENES = [
  {
    id: '01_old_way_pain',
    title: 'Table chaos before the run',
    duration: 6,
    prompt: 'Photoreal cinematic cyberpunk tabletop RPG session at night, rain on windows, cluttered table with dice, maps, old laptops, character sheets, snacks, and tense players trying to start a run, diverse metahuman-inspired cast with subtle cyberware, expressive acting, handheld trailer energy, moody practical lighting, no readable product text anywhere.',
  },
  {
    id: '02_chummer6_reveal',
    title: 'The campaign console opens',
    duration: 6,
    prompt: 'Photoreal product hero reveal in the same rainy cyberpunk safehouse, a focused decker opens a sleek dark tabletop campaign desktop client with no readable product name, compact character and session panels glow on faces, the team shifts from chaos to confidence, cinematic push-in, premium roleplaying trailer energy, no generated words or logos.',
  },
  {
    id: '03_build_runner',
    title: 'Build the runner',
    duration: 8,
    prompt: 'Strict photoreal live-action cyberpunk tabletop product trailer, over-the-shoulder workflow montage at a real dark gaming table, adult metahuman-inspired runners and a GM in practical costumes, visible cyberware implants, compact desktop character builder UI with attributes, skills, cyberware, magic choices, contacts, gear, and derived stats updating on a dense monitor, mouse-driven edits, practical monitor light, sharp premium commercial cinematography, serious grounded actors, no readable labels.',
  },
  {
    id: '04_explain_values',
    title: 'Know why the number changed',
    duration: 8,
    prompt: 'Strict photoreal live-action cinematic product demo at the same cyberpunk tabletop, elf-inspired mage player with subtle prosthetic ears and AR contact lens inspects a value change on a compact dark desktop UI, a clean side panel unfolds with abstract calculation blocks and highlighted dependencies, no copyrighted source text, the player nods because the sheet finally makes sense, elegant restrained UI, real actors, practical neon and table light, no readable labels.',
  },
  {
    id: '05_black_ledger_alive',
    title: 'The city wakes up',
    duration: 8,
    prompt: 'Strict photoreal live-action cyberpunk GM command room, adult tabletop crew and GM around a real command table, a massive high-end living city map interface floats above the table with glowing districts, heat arcs, job seeds, incident markers and pressure pulses, no faction branding, the table watches the campaign world react to their run, dramatic reveal, strategy-game scale, cinematic orbiting camera, practical smoke and neon, no readable text.',
  },
  {
    id: '06_release_truth',
    title: 'Prep without rummaging',
    duration: 8,
    prompt: 'Photoreal GM prep montage in a cyberpunk tabletop command interface, session notes, NPC cards, loot, scene clocks, opposition, maps, and handouts snap into one clean workspace, seasoned GM smiles because prep is finally under control, premium dramatic lighting, practical mouse and keyboard actions, no audit dashboard, no release dashboard, no readable text.',
  },
  {
    id: '07_table_pulse',
    title: 'Table Pulse',
    duration: 8,
    prompt: 'Photoreal tabletop RPG session in progress, players around a real table with dice, tactical maps, minis, and laptops, GM screen receives a subtle abstract heat-and-consequence alert, players react to the table pressure, cinematic closeups, warm table light and cyberpunk accents, no readable labels.',
  },
  {
    id: '08_world_reacts',
    title: 'The world pushes back',
    duration: 8,
    prompt: 'Photoreal split-scene cyberpunk gameplay moment, remote player with visible cyberware receives an abstract campaign reaction on phone, taps a response, GM desktop updates with a consequence card, product feature focus, crisp minimal AR overlays, cinematic tension, no faction identities, no readable text.',
  },
  {
    id: '09_karma_forge',
    title: 'Karma Forge',
    duration: 8,
    prompt: 'Photoreal premium tabletop product scene showing a house-rule packet being proposed, compared, reviewed, and accepted at the table, compact desktop UI with abstract cards and toggles, players debate and laugh, GM keeps control, grounded elegant product cinematography, no readable labels.',
  },
  {
    id: '10_newsroom',
    title: 'Newsreels',
    duration: 8,
    prompt: 'Photoreal premium futuristic in-world newsroom, charismatic ork-inspired news anchor delivers satirical fallout of a tabletop run, giant incident screens and ticker-like abstract visuals behind anchor, polished broadcast lighting, true TV-news framing, no canon logos, no faction content, no readable text.',
  },
  {
    id: '11_play_anywhere',
    title: 'Play anywhere',
    duration: 6,
    prompt: 'Strict photoreal live-action device continuity montage, adult cyberpunk tabletop players with visible cyberware pass campaign state from compact Windows desktop client to tablet and phone PWA, same runner sheet and campaign state preserved, mouse and touch interactions visible, restrained premium dark UI, real devices, cinematic closeups, no marketing page look, no readable product names.',
  },
  {
    id: '12_hero_ending',
    title: 'The crew hits the street',
    duration: 8,
    prompt: 'Photoreal cinematic hero ending on rainy neon cyberpunk city street at night, recurring tabletop crew steps out confident and ready for the next run, reflections, chrome, subtle holographic glow, confident roleplaying-table energy, emotional but witty finish, premium trailer quality, no generated product title or readable text.',
  },
];

function scenePath(scene, suffix) {
  return path.join(OUT_DIR, `${scene.id}${suffix}`);
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
  await box.click({ timeout: 10000 });
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.insertText(prompt);
  await page.waitForTimeout(800);
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
  return [...new Set((text.match(/https:\/\/(?:cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/[^"'\s<>]+?\.(?:mp4|webm)/g) || [])
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
    if (/(?:cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/.*\.(mp4|webm)/.test(found)) urls.add(found);
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

async function renderScene(page, scene) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const mp4Path = scenePath(scene, '.mp4');
  const sidecarPath = scenePath(scene, '.magicfit.json');
  if (fs.existsSync(mp4Path) && fs.existsSync(sidecarPath) && !process.argv.includes('--force')) {
    console.log(`skip ${scene.id}`);
    return;
  }

  const events = [];
  const seenVideoUrls = new Set();
  page.on('response', async (response) => {
    const url = response.url();
    if (!url.includes('magicfit') && !url.includes('pushowl')) return;
    const item = { status: response.status(), url, contentType: response.headers()['content-type'] || '' };
    events.push(item);
    if (/(?:cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/.*\.(mp4|webm)(?:$|\?)/.test(url)) seenVideoUrls.add(url);
    const ct = item.contentType;
    if (/json|script|text/.test(ct)) {
      const text = await response.text().catch(() => '');
      for (const found of collectCdnVideoUrlsFromText(text)) seenVideoUrls.add(found);
    }
  });

  await page.goto('https://magicfit.pushowl.com/agents/generate?mode=video', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(5000);
  const baselineVideoUrls = await collectVisibleMagicFitVideoUrls(page);
  await selectPill(page, '9:16', 'Landscape (16:9)').catch(async () => {
    await page.locator('select').nth(0).selectOption('16:9').catch(() => {});
  });
  await selectPill(page, '4s', `${scene.duration}s`).catch(async () => {
    await page.locator('select').nth(1).selectOption(String(scene.duration)).catch(() => {});
  });
  const fullPrompt = `${scene.prompt} Global constraints: ${GLOBAL_NEGATIVE}.`;
  await fillPrompt(page, fullPrompt);
  await page.screenshot({ path: scenePath(scene, '.before-submit.png'), fullPage: true });
  const submit = page.locator('form button').last();
  const submittedAtMs = Date.now();
  await submit.click({ timeout: 30000 });
  console.log(`submitted ${scene.id}`);
  await page.waitForTimeout(3000);

  const deadline = Date.now() + 18 * 60 * 1000;
  let videoUrl = null;
  while (Date.now() < deadline && !videoUrl) {
    await page.waitForTimeout(10000);
    const html = await page.content().catch(() => '');
    for (const found of collectCdnVideoUrlsFromText(html)) seenVideoUrls.add(found);
    const videos = await page.locator('video').evaluateAll((nodes) => nodes.map((v) => v.currentSrc || v.src).filter(Boolean)).catch(() => []);
    for (const found of videos) {
      if (/(?:cdn\.pushowl\.com|media\.powlcdn\.com)\/magicfit\/.*\.(mp4|webm)/.test(found)) seenVideoUrls.add(found);
    }
    videoUrl = chooseNewestVideoUrl(seenVideoUrls, baselineVideoUrls, submittedAtMs);
    if (!videoUrl) console.log(`poll ${scene.id}: waiting`);
  }
  await page.screenshot({ path: scenePath(scene, '.after-render.png'), fullPage: true }).catch(() => {});
  if (!videoUrl) {
    fs.writeFileSync(scenePath(scene, '.failed.json'), JSON.stringify({ scene, events: events.slice(-200), url: page.url() }, null, 2));
    throw new Error(`No MagicFit video URL found for ${scene.id}`);
  }
  await download(videoUrl, mp4Path);
  const sidecar = {
    provider: 'MagicFit',
    rendered_by: 'EA MagicFit browser automation',
    scene_id: scene.id,
    title: scene.title,
    duration_seconds_requested: scene.duration,
    aspect_ratio: '16:9',
    resolution: '720p',
    model: 'Seedance 2.0 Fast',
    video_output_url: videoUrl,
    source_prompt: fullPrompt,
    faction_assets_used: false,
    direct_publish: false,
    generated_at_utc: new Date().toISOString(),
    page_url_after_submit: page.url(),
    event_tail: events.slice(-80),
  };
  fs.writeFileSync(sidecarPath, JSON.stringify(sidecar, null, 2));
  console.log(`rendered ${scene.id} -> ${mp4Path}`);
}

async function main() {
  const onlyIdx = process.argv.indexOf('--only');
  const only = onlyIdx >= 0 ? new Set(process.argv[onlyIdx + 1].split(',').map((s) => s.trim())) : null;
  const scenes = only ? SCENES.filter((scene) => only.has(scene.id) || only.has(scene.id.slice(0, 2))) : SCENES;
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
  const page = await context.newPage();
  await login(page);
  for (const scene of scenes) {
    await renderScene(page, scene);
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
