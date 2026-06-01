const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

const OUT_DIR = '/docker/chummercomplete/_completion/horizons_90s_promo/magicfit_clips';
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

const GLOBAL_POSITIVE = [
  'Photoreal cinematic cyberpunk tabletop roleplaying product teaser',
  'realistic mixed metahuman tabletop crew: human GM, ork decker, elf mage, dwarf rigger, troll street samurai, human face',
  'visible cyberware on multiple characters: chrome cyberarm, AR lenses, datajack, subtle dermal plating, neural interface lights',
  'augmented reality overlays floating above the table and devices',
  'expressive acting',
  'real action in every shot',
  'premium dark neon lighting',
  'rain reflections',
  'practical lights',
  'high-end trailer quality',
  'product UI overlays will be added in post',
].join(', ');

const GLOBAL_NEGATIVE = [
  'SVG',
  'flat vector animation',
  'static poster',
  'slideshow',
  'generic SaaS explainer',
  'generic office',
  'no people',
  'frozen faces',
  'plastic skin',
  'distorted hands',
  'unreadable AI text',
  'long paragraphs on screen',
  'official Shadowrun logos',
  'official corporation or faction marks',
  'sourcebook art',
  'sourcebook page designs',
  'canonical named characters',
  'real celebrity likeness',
  'provider watermark',
].join(', ');

const SCENES = [
  {
    id: '01_cold_open_table_chaos',
    horizon: 'framing',
    title: 'The table is alive, but the tools are dead',
    duration: 6,
    prompt: 'Rain-lit safehouse tabletop game, messy paper sheets, tablets, dice, misaligned AR notes, human GM trying to regain context, ork decker with AR lenses, elf mage, dwarf rigger with headset, troll street samurai with chrome cyberarm, visible cyberware and funny frustration, handheld cinematic inserts.',
  },
  {
    id: '02_nexus_pan_shared_state',
    horizon: 'NEXUS-PAN',
    title: 'Reconnect without losing the table',
    duration: 8,
    prompt: 'A player phone reconnects, session state snaps into sync across laptop tablet and mobile, bright AR data strands align over the table, ork decker with datajack and AR lenses, troll street samurai with cyberarm, relieved mixed-metahuman character reactions, practical neon table light.',
  },
  {
    id: '03_alice_build_tradeoffs',
    horizon: 'ALICE',
    title: 'Legal is not the same as good',
    duration: 8,
    prompt: 'AR build lab above a tabletop, two generic cyberpunk runner builds compared as clean holographic silhouettes and risk badges, ork decker with AR lenses reacts, elf mage smirks, visible cyberware reflections, no dense text, premium product trailer closeup.',
  },
  {
    id: '04_karma_forge_governed_rules',
    horizon: 'KARMA FORGE',
    title: 'House rules without fork chaos',
    duration: 8,
    prompt: 'GM manipulates holographic AR rule cards and approval stamps, impacted runner sheets glow, troll street samurai with chrome cyberarm reacts to a flagged weapon, dwarf rigger and elf mage visible at table, cinematic overhead and UI closeup.',
  },
  {
    id: '05_jackpoint_dossiers_recaps',
    horizon: 'JACKPOINT',
    title: 'Briefings that remember where facts came from',
    duration: 8,
    prompt: 'Cyberpunk evidence room, rough mission notes become a polished player-safe AR dossier packet, source trails glow under claims, stylish human fixer with subtle cybernetic eye reacts, ork decker and elf mage nearby, noir push-in, no readable paragraphs.',
  },
  {
    id: '06_runsite_spatial_prep',
    horizon: 'RUNSITE',
    title: 'Understand the space before it explodes',
    duration: 8,
    prompt: '3D AR model of a generic clinic or warehouse unfolds above tabletop, entry points and security zones as abstract geometry, GM-only hidden layer flashes, dwarf rigger with visible cybernetic hand points at a drone nest, troll and ork silhouettes nearby.',
  },
  {
    id: '07_runbook_press_campaign_books',
    horizon: 'RUNBOOK PRESS',
    title: 'Turn a season into a book',
    duration: 8,
    prompt: 'Futuristic publishing room, AR campaign maps and faction-neutral briefs flow into a premium original book mockup, mixed human ork elf dwarf troll tabletop crew watching with pride, visible cyberware and AR lenses, no sourcebook layout imitation.',
  },
  {
    id: '08_table_pulse_live_heat',
    horizon: 'TABLE PULSE',
    title: 'The run pushes back',
    duration: 8,
    prompt: 'Tabletop session in motion with mixed metahuman crew, GM screen receives a subtle AR heat alert, remote player chooses a bounded reaction on phone, ork decker with AR lenses and troll cyberarm visible, cast reacts to fallout, warm table light and cyberpunk accents.',
  },
  {
    id: '09_black_ledger_living_world',
    horizon: 'BLACK LEDGER',
    title: 'The city remembers',
    duration: 10,
    prompt: 'Premium living city globe and district map AR interface, generic faction pressure shown as abstract heat arcs, completed run changes city markers and newsroom ticker energy, mixed metahuman operators with visible cyberware watch the globe, cinematic orbiting camera.',
  },
  {
    id: '10_community_hub_open_runs',
    horizon: 'COMMUNITY HUB',
    title: 'Find the table. Close the loop.',
    duration: 8,
    prompt: 'Open-run recruitment scene, human ork elf dwarf and troll players gather around a table through phones and laptops, AR preflight checks glow green as abstract cards, visible cyberware, calendar handoff, welcoming character moment.',
  },
  {
    id: '11_finale_all_horizons',
    horizon: 'all',
    title: 'All Horizons, one table',
    duration: 10,
    prompt: 'All nine Horizon AR cards circle above the tabletop and become a living city interface, recurring mixed metahuman cast stands together: human GM, ork decker, elf mage, dwarf rigger, troll street samurai with cyberarm, visible cyberware, final product logo space left clean for post, heroic trailer finish.',
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
  return [...new Set((text.match(/https:\/\/cdn\.pushowl\.com\/magicfit\/[^"'\s<>]+?\.(?:mp4|webm)/g) || [])
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
    if (/cdn\.pushowl\.com\/magicfit\/.*\.(mp4|webm)/.test(found)) urls.add(found);
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
    if (/cdn\.pushowl\.com\/magicfit\/.*\.(mp4|webm)(?:$|\?)/.test(url)) seenVideoUrls.add(url);
    if (/json|script|text/.test(item.contentType)) {
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
  const fullPrompt = `${GLOBAL_POSITIVE}. Scene ${scene.id}, ${scene.horizon}: ${scene.prompt} Constraints: ${GLOBAL_NEGATIVE}.`;
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
      if (/cdn\.pushowl\.com\/magicfit\/.*\.(mp4|webm)/.test(found)) seenVideoUrls.add(found);
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
    asset_id: 'all-horizons-90s-magicfit-promo',
    scene_id: scene.id,
    horizon: scene.horizon,
    title: scene.title,
    duration_seconds_requested: scene.duration,
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
